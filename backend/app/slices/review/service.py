"""审查业务逻辑（M2 的 C 组）。

**服务层不依赖 HTTP**：接收普通参数、抛 `BusinessError`、返回普通对象。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import to_iso
from app.core.errors import BusinessError, ErrorCode
from app.infra.storage import get_storage
from app.models.contract import Contract, ContractVersion
from app.models.file import FileObject
from app.models.review import ReviewReport, ReviewTask, RiskPoint
from app.slices.review.pipeline import run_review_pipeline
from app.slices.review.schemas import (
    CreateReviewRequest,
    ReviewCounts,
    ReviewListItem,
    ReviewResultData,
    ReviewTaskData,
    RiskPointData,
)

_ACTIVE_STATUSES = ("pending", "processing")
_ALL_STATUSES = ("pending", "processing", "succeeded", "failed")
_MAX_PAGE_SIZE = 100

_SORT_OPTIONS = {
    "-created_at": ReviewTask.created_at.desc(),
    "created_at": ReviewTask.created_at.asc(),
    "-finished_at": ReviewTask.finished_at.desc(),
    "finished_at": ReviewTask.finished_at.asc(),
}


# ============================================================
# C-01 发起审查
# ============================================================


def create_task(db: Session, *, user_id: int, payload: CreateReviewRequest) -> ReviewTaskData:
    file_object = _load_file(db, file_id=payload.file_id)
    version = _ensure_contract_version(
        db, user_id=user_id, file_object=file_object, title=payload.contract_title
    )

    if not payload.force:
        running = db.scalar(
            select(ReviewTask.id).where(
                ReviewTask.contract_version_id == version.id,
                ReviewTask.status.in_(_ACTIVE_STATUSES),
                ReviewTask.deleted_at.is_(None),
            )
        )
        if running:
            raise BusinessError(ErrorCode.REVIEW_IN_PROGRESS, "该文件正在审查中，请等待完成或使用 force 重试")

    task = ReviewTask(
        contract_id=version.contract_id,
        contract_version_id=version.id,
        user_id=user_id,
        status="pending",
        progress=0,
    )
    db.add(task)
    db.flush()
    return _to_task_data(task)


def _load_file(db: Session, *, file_id: str) -> FileObject:
    """按 ID 取文件对象。

    ⚠️ **刻意不校验 `uploader_id`**，两个理由：

    1. **契约要求**：`docs/05 §5.4` 给 C-01 规定的错误码只有
       `40001` / `40404` / `40905` / `42901`，**没有 `40301`** ——
       即该接口本就不该因"文件不是你的"而拒绝。
    2. **语义要求**：`uploader_id` 记录的是"谁**最先**上传了这个内容"，
       **不代表文件属于他**（`docs/04 §5.1` 原文）。内容寻址是全局去重的，
       第二个用户上传同一份合同会拿到同一个 `file_object` ——
       若按 `uploader_id` 鉴权，他反而无法审查自己刚上传的文件。

    **归属由业务表决定**：审查任务的归属是 `review_task.user_id`，
    合同的归属是 `contract.owner_id`，两者都在本函数之外的层级校验。
    """
    try:
        numeric_id = int(file_id)
    except (TypeError, ValueError) as exc:
        raise BusinessError(ErrorCode.PARAM_INVALID, "file_id 不合法") from exc

    file_object = db.get(FileObject, numeric_id)
    if file_object is None or file_object.deleted_at is not None:
        raise BusinessError(ErrorCode.FILE_NOT_FOUND, "文件不存在")
    return file_object


def _ensure_contract_version(
    db: Session, *, user_id: int, file_object: FileObject, title: str | None
) -> ContractVersion:
    """找到该文件对应的合同版本；没有就建合同与首个版本。

    ⚠️ `contract_version` **不可变**：重审同一文件复用同一个版本，
    而不是每次新建 —— 否则"这份报告对应哪一版文本"就说不清了。
    """
    existing = db.scalar(
        select(ContractVersion)
        .join(Contract, Contract.id == ContractVersion.contract_id)
        .where(ContractVersion.file_object_id == file_object.id, Contract.owner_id == user_id)
    )
    if existing is not None:
        return existing

    contract = Contract(
        owner_id=user_id,
        title=(title or file_object.original_name or "未命名合同")[:200],
        status="draft",
        source="upload",
    )
    db.add(contract)
    db.flush()

    version = ContractVersion(
        contract_id=contract.id,
        version_no=1,
        file_object_id=file_object.id,
        created_by=user_id,
    )
    db.add(version)
    db.flush()
    contract.current_version_id = version.id
    db.flush()
    return version


def enqueue(task_id: int) -> None:
    """登记并执行审后台任务。

    ⚠️ 单独成函数是为了**让测试可以替换它** —— 测试里不应真的跑流水线
    （那会去调用 AI 封装）。生产路径由路由层通过 `BackgroundTasks` 触发。
    """
    run_review_pipeline(task_id)


# ============================================================
# C-02 查询状态
# ============================================================


def get_task(db: Session, *, user_id: int, task_id: int) -> ReviewTaskData:
    return _to_task_data(_load_owned_task(db, user_id=user_id, task_id=task_id))


def _load_owned_task(db: Session, *, user_id: int, task_id: int) -> ReviewTask:
    task = db.get(ReviewTask, task_id)
    if task is None or task.deleted_at is not None:
        raise BusinessError(ErrorCode.REVIEW_NOT_FOUND, "审查任务不存在")
    if task.user_id != user_id:
        raise BusinessError(ErrorCode.FORBIDDEN, "无权访问该审查任务")
    return task


def _to_task_data(task: ReviewTask) -> ReviewTaskData:
    return ReviewTaskData(
        task_id=str(task.id),
        status=task.status,  # type: ignore[arg-type]
        stage=task.stage,
        progress=task.progress,
        error_code=task.error_code,
        error_message=task.error_message,
        started_at=to_iso(task.started_at),
        finished_at=to_iso(task.finished_at),
        created_at=to_iso(task.created_at),
    )


# ============================================================
# C-03 获取结果
# ============================================================


def get_result(db: Session, *, user_id: int, task_id: int) -> ReviewResultData:
    task = _load_owned_task(db, user_id=user_id, task_id=task_id)
    _require_finished(task)

    points = _load_risk_points(db, task_id=task.id)
    return ReviewResultData(
        task_id=str(task.id),
        contract_title=_contract_title(db, task),
        summary=task.report.summary if task.report else None,
        counts=_counts_from(points),
        extracted_terms=task.extracted_terms,
        risk_points=[_to_point_data(point) for point in points],
    )


def _require_finished(task: ReviewTask) -> None:
    if task.status == "failed":
        raise BusinessError(ErrorCode.REVIEW_FAILED, task.error_message or "审查任务执行失败")
    if task.status != "succeeded":
        raise BusinessError(ErrorCode.REVIEW_NOT_FINISHED, "审查任务尚未完成")


def _load_risk_points(db: Session, *, task_id: int) -> list[RiskPoint]:
    return list(
        db.scalars(
            select(RiskPoint)
            .where(RiskPoint.review_task_id == task_id, RiskPoint.deleted_at.is_(None))
            .order_by(RiskPoint.id.asc())
        ).all()
    )


def _counts_from(points: list[RiskPoint]) -> ReviewCounts:
    counts = ReviewCounts()
    for point in points:
        if point.risk_level == "high":
            counts.high += 1
        elif point.risk_level == "medium":
            counts.medium += 1
        elif point.risk_level == "low":
            counts.low += 1
    return counts


def _to_point_data(point: RiskPoint) -> RiskPointData:
    return RiskPointData(
        id=str(point.id),
        risk_level=point.risk_level,  # type: ignore[arg-type]
        risk_category=point.risk_category,
        clause_title=point.clause_title,
        clause_text=point.clause_text,
        char_start=point.char_start,
        char_end=point.char_end,
        description=point.description,
        suggestion=point.suggestion,
        legal_basis=point.legal_basis,
        source_type=point.source_type,  # type: ignore[arg-type]
        confidence=float(point.confidence) if point.confidence is not None else None,
        is_dismissed=point.is_dismissed,
    )


def _contract_title(db: Session, task: ReviewTask) -> str | None:
    if task.contract_id is None:
        return None
    contract = db.get(Contract, task.contract_id)
    return contract.title if contract else None


# ============================================================
# C-04 下载报告
# ============================================================


def get_report(db: Session, *, user_id: int, task_id: int) -> tuple[str, bytes]:
    """返回 (文件名, PDF 字节)。"""
    task = _load_owned_task(db, user_id=user_id, task_id=task_id)
    _require_finished(task)

    report = db.scalar(
        select(ReviewReport).where(ReviewReport.review_task_id == task.id, ReviewReport.deleted_at.is_(None))
    )
    if report is None or report.file_object_id is None:
        raise BusinessError(ErrorCode.REVIEW_NOT_FOUND, "审查报告不存在")
    file_object = db.get(FileObject, report.file_object_id)
    if file_object is None or file_object.deleted_at is not None:
        raise BusinessError(ErrorCode.REVIEW_NOT_FOUND, "审查报告文件不存在")

    filename = file_object.original_name or f"review-{task.id}.pdf"
    return filename, get_storage().get(file_object.object_key)


# ============================================================
# C-05 审查历史
# ============================================================


def list_tasks(
    db: Session,
    *,
    user_id: int,
    page: int,
    page_size: int,
    status: str | None,
    sort: str,
) -> tuple[list[ReviewListItem], int]:
    if page < 1 or page_size < 1 or page_size > _MAX_PAGE_SIZE:
        raise BusinessError(
            ErrorCode.PAGE_OUT_OF_RANGE, f"分页参数超出范围（page_size 上限 {_MAX_PAGE_SIZE}）"
        )
    if status is not None and status not in _ALL_STATUSES:
        raise BusinessError(ErrorCode.PARAM_INVALID, "status 取值不合法")
    order_by = _SORT_OPTIONS.get(sort)
    if order_by is None:
        raise BusinessError(ErrorCode.PARAM_INVALID, "sort 取值不合法")

    conditions = [ReviewTask.user_id == user_id, ReviewTask.deleted_at.is_(None)]
    if status is not None:
        conditions.append(ReviewTask.status == status)

    total = db.scalar(select(func.count()).select_from(ReviewTask).where(*conditions)) or 0
    tasks = db.scalars(
        select(ReviewTask)
        .where(*conditions)
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [_to_list_item(db, task) for task in tasks]
    return items, int(total)


def _to_list_item(db: Session, task: ReviewTask) -> ReviewListItem:
    report = db.scalar(
        select(ReviewReport).where(ReviewReport.review_task_id == task.id, ReviewReport.deleted_at.is_(None))
    )
    counts = (
        ReviewCounts(high=report.high_count, medium=report.medium_count, low=report.low_count)
        if report is not None
        else ReviewCounts()
    )
    return ReviewListItem(
        task_id=str(task.id),
        contract_title=_contract_title(db, task),
        status=task.status,  # type: ignore[arg-type]
        counts=counts,
        created_at=to_iso(task.created_at) or "",
        finished_at=to_iso(task.finished_at),
    )


# ============================================================
# C-06 标记误报
# ============================================================


def dismiss_risk_point(
    db: Session, *, user_id: int, task_id: int, point_id: int, is_dismissed: bool
) -> RiskPointData:
    task = _load_owned_task(db, user_id=user_id, task_id=task_id)
    point = db.get(RiskPoint, point_id)
    if point is None or point.deleted_at is not None or point.review_task_id != task.id:
        raise BusinessError(ErrorCode.REVIEW_NOT_FOUND, "风险点不存在")
    point.is_dismissed = is_dismissed
    db.flush()
    return _to_point_data(point)
