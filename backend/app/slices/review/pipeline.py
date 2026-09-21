"""审查流水线（异步执行）。

**连接方式是"创建任务 + 轮询"**（03-概要设计 §5.1），不使用 WebSocket、
不引入消息队列。执行体是**同步函数**，由 FastAPI 的 `BackgroundTasks` 放进
线程池运行 —— 写成 `async def` 会让 pypdf / 网络调用阻塞事件循环。

⚠️ **每个阶段结束都要 `commit`**：轮询接口用另一个数据库会话读取进度，
若不提交，用户在整个审查期间都只能看到 `pending`。

⚠️ **本文件不实现任何 AI 能力**，只调用 `app/infra/llm.py`、`ocr.py`、`vector.py`
的封装。AI 队友替换这些封装的内部实现即可，本文件无需改动。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import now_beijing
from app.core.errors import BusinessError, ErrorCode
from app.infra import llm, ocr, parsing, vector
from app.infra.concurrency import pipeline_gate
from app.infra.db.session import SessionLocal
from app.infra.parsing import detect_format
from app.infra.storage import get_storage, object_key_for, sha256_of
from app.models.contract import ContractVersion
from app.models.file import FileObject
from app.models.knowledge import RiskRule
from app.models.review import ReviewReport, ReviewTask, RiskPoint
from app.slices.review import prompts
from app.slices.review.report import build_report_pdf

logger = logging.getLogger("lawwiz.review")

# `stage` 的取值与 05-接口设计 §5.4 的 C-02 逐字一致
STAGE_OCR = "ocr"
STAGE_EXTRACT = "extract_terms"
STAGE_RETRIEVE = "retrieve"
STAGE_ANALYZE = "analyze"
STAGE_REPORT = "report"

_STAGE_PROGRESS = {
    STAGE_OCR: 15,
    STAGE_EXTRACT: 40,
    STAGE_RETRIEVE: 60,
    STAGE_ANALYZE: 85,
    STAGE_REPORT: 95,
}

_SOURCE_TYPES = {"retrieved_law", "rule", "llm_inference"}
_RISK_LEVELS = {"high", "medium", "low"}


@dataclass
class _Context:
    """阶段之间传递中间结果。**不落库**，只服务于本次执行。"""

    text: str = ""
    text_source: str | None = None
    terms: dict[str, Any] = field(default_factory=dict)
    legal_basis: list[dict[str, Any]] = field(default_factory=list)
    rules: list[RiskRule] = field(default_factory=list)
    risk_points: list[dict[str, Any]] = field(default_factory=list)


def run_review_pipeline(task_id: int) -> None:
    """流水线入口。**异常一律转成任务的失败状态**，绝不向外抛出。"""
    db = SessionLocal()
    # ⚠️ 并发闸门（见 app/infra/concurrency.py）必须在**第一次用数据库之前**取得：
    # SessionLocal() 是惰性的（首次查询才占连接），所以此刻还没占用连接池 ——
    # 若先查库再排队，等待者会先把手里的连接占住，反而加剧连接池耗尽。
    if not pipeline_gate.acquire():
        _mark_failed(db, task_id, str(int(ErrorCode.RATE_LIMITED)), "服务繁忙，请稍后重试")
        db.close()
        return
    try:
        task = db.get(ReviewTask, task_id)
        if task is None:
            logger.warning("审查任务 %s 不存在，跳过执行", task_id)
            return

        task.status = "processing"
        task.started_at = now_beijing()
        task.error_code = None
        task.error_message = None
        db.commit()

        context = _Context()
        stages = (
            (STAGE_OCR, _stage_ocr),
            (STAGE_EXTRACT, _stage_extract),
            (STAGE_RETRIEVE, _stage_retrieve),
            (STAGE_ANALYZE, _stage_analyze),
            (STAGE_REPORT, _stage_report),
        )
        for stage, handler in stages:
            # 先写进度再执行：让轮询能看到"正在做哪一步"
            task.stage = stage
            task.progress = _STAGE_PROGRESS[stage]
            db.commit()
            handler(db, task, context)
            db.commit()

        task.status = "succeeded"
        task.stage = None
        task.progress = 100
        task.finished_at = now_beijing()
        db.commit()
        logger.info("审查任务 %s 完成，风险点 %d 条", task_id, len(context.risk_points))

    except BusinessError as exc:
        _mark_failed(db, task_id, str(int(exc.code)), exc.message)
    except Exception:
        # 兜底：未预料的异常也要落成失败状态，否则任务会永远停在 processing
        logger.exception("审查任务 %s 执行失败", task_id)
        _mark_failed(db, task_id, str(int(ErrorCode.INTERNAL_ERROR)), "服务器内部错误，审查未能完成")
    finally:
        db.close()
        pipeline_gate.release()


def _mark_failed(db: Session, task_id: int, code: str, message: str) -> None:
    try:
        db.rollback()
        task = db.get(ReviewTask, task_id)
        if task is None:
            return
        task.status = "failed"
        task.error_code = code
        task.error_message = message
        task.finished_at = now_beijing()
        db.commit()
    except Exception:
        logger.exception("写入任务 %s 的失败状态时又出错了", task_id)


# ============================================================
# 阶段一：文本化（M2-02）
# ============================================================


def _stage_ocr(db: Session, task: ReviewTask, ctx: _Context) -> None:
    version = db.get(ContractVersion, task.contract_version_id) if task.contract_version_id else None
    if version is None:
        raise BusinessError(ErrorCode.REVIEW_FAILED, "合同版本不存在，无法审查")

    if version.plain_text:
        # 同一版本重审时复用已提取的文本，不重复解析
        ctx.text = version.plain_text
        ctx.text_source = version.text_source
        return

    file_object = db.get(FileObject, version.file_object_id) if version.file_object_id else None
    if file_object is None:
        raise BusinessError(ErrorCode.FILE_NOT_FOUND, "合同文件不存在或已被删除")

    try:
        data = get_storage().get(file_object.object_key)
    except BusinessError as exc:
        # 数据库有记录、对象存储却没有内容 —— 说明两边不一致（人为清理、迁移
        # 未同步、对象存储丢数据等）。给出**可操作**的指引，而不是只说"不存在"。
        raise BusinessError(
            ErrorCode.FILE_NOT_FOUND,
            "合同文件内容已不存在（数据库记录与对象存储不一致），请重新上传该文件后再发起审查",
        ) from exc
    fmt = detect_format(data)
    if fmt is None:
        raise BusinessError(ErrorCode.UNSUPPORTED_FILE_TYPE, "文件格式无法识别，无法提取文本")

    source = "parse"
    text = ""
    page_count: int | None = None
    if fmt.is_text_extractable:
        parsed = parsing.extract_text(data, fmt)
        if parsed is not None:
            text = parsed.text
            page_count = parsed.page_count

    if not text.strip():
        # 走到这里有两种情况：① 图片文件（本来就该 OCR）；② **扫描版 PDF** ——
        # 文件头是 PDF 但没有文本层。二者都要交给 OCR，不能直接判定"无内容"。
        text = ocr.ocr_extract_text(data)
        source = "ocr"

    if not text.strip():
        raise BusinessError(ErrorCode.REVIEW_FAILED, "未能从该文件中提取到任何文本")

    ctx.text = text
    ctx.text_source = source
    version.plain_text = text
    version.text_source = source
    version.page_count = page_count


# ============================================================
# 阶段二：关键条款提取（M2-03）
# ============================================================


def _stage_extract(db: Session, task: ReviewTask, ctx: _Context) -> None:
    result = llm.complete_structured(
        prompts.TERMS_SYSTEM,
        prompts.TERMS_USER_TEMPLATE.format(text=ctx.text[: prompts.MAX_TEXT_CHARS]),
        prompts.TERMS_SCHEMA,
    )
    ctx.terms = result if isinstance(result, dict) else {}
    task.extracted_terms = ctx.terms
    task.raw_llm_output = {"extract_terms": ctx.terms}


# ============================================================
# 阶段三：检索法律依据与风险规则（M2-04）
# ============================================================


def _stage_retrieve(db: Session, task: ReviewTask, ctx: _Context) -> None:
    query = " ".join(
        str(ctx.terms.get(key))
        for key in ("liability", "payment_terms", "amount", "jurisdiction")
        if ctx.terms.get(key)
    )
    hits = vector.search(query or ctx.text[:200], top_k=5)
    ctx.legal_basis = [
        {"doc_id": hit.doc_id, "chunk_id": hit.chunk_id, "text": hit.text, "score": hit.score} for hit in hits
    ]
    ctx.rules = _match_rules(db, ctx.text)


def _match_rules(db: Session, text: str) -> list[RiskRule]:
    """按关键词匹配启用的风险规则。

    **这一步是确定性的**（纯字符串匹配，不涉及模型），它是 AI 失效时
    可解释结论的来源（03-概要设计 §5.3）。
    """
    rules = db.scalars(
        select(RiskRule).where(RiskRule.is_active.is_(True), RiskRule.deleted_at.is_(None))
    ).all()
    matched: list[RiskRule] = []
    for rule in rules:
        keywords = [k.strip() for k in (rule.match_keywords or "").split(",") if k.strip()]
        if keywords and any(keyword in text for keyword in keywords):
            matched.append(rule)
    return matched


# ============================================================
# 阶段四：风险分析（M2-05）
# ============================================================


def _stage_analyze(db: Session, task: ReviewTask, ctx: _Context) -> None:
    legal_basis_text = "\n".join(f"- {hit['text']}" for hit in ctx.legal_basis) or "（未检索到相关法条）"
    rules_text = (
        "\n".join(
            f"- {r.rule_code} {r.name}：{r.conclusion}（依据：{r.legal_basis or '未标注'}）"
            for r in ctx.rules
        )
        or "（未命中审查规则）"
    )

    result = llm.complete_structured(
        prompts.ANALYZE_SYSTEM,
        prompts.ANALYZE_USER_TEMPLATE.format(
            terms=ctx.terms,
            legal_basis=legal_basis_text,
            rules=rules_text,
            text=ctx.text[: prompts.MAX_TEXT_CHARS],
        ),
        prompts.ANALYZE_SCHEMA,
    )
    raw_points = result.get("risk_points") if isinstance(result, dict) else None
    points = raw_points if isinstance(raw_points, list) else []

    # ⚠️ **先单独提交一次清理，再写入新的风险点。**
    #
    # 原因（实测结论）：同一文件的并发审查是**契约允许**的（C-01 的 `force=true`）。
    # 若 DELETE 与 INSERT 同处一个事务，DELETE 会在 `risk_point.review_task_id`
    # 索引上留下**间隙锁**，与另一事务对同表索引的 INSERT 形成循环等待 →
    # MySQL `1213 Deadlock`，任务以 50000 失败。
    # 实测：5 个同文件并发审查中有 2 个因死锁失败。
    # 把 DELETE 放进独立事务（此处 commit），间隙锁在插入前即释放，循环等待不成立。
    #
    # 清理本身是为"重跑同一任务"准备的（正常流程每个任务只跑一次）。
    db.execute(delete(RiskPoint).where(RiskPoint.review_task_id == task.id))
    db.commit()

    ctx.risk_points = [_normalize_point(p) for p in points if isinstance(p, dict)]
    for point in ctx.risk_points:
        db.add(RiskPoint(review_task_id=task.id, **_point_columns(point)))

    task.raw_llm_output = {"extract_terms": ctx.terms, "analyze": points}


def _normalize_point(raw: dict[str, Any]) -> dict[str, Any]:
    """把模型输出收敛到契约允许的取值，**不因模型不守约而让任务失败**。"""
    level = str(raw.get("risk_level") or "").strip().lower()
    source = str(raw.get("source_type") or "").strip().lower()
    point = dict(raw)
    point["risk_level"] = level if level in _RISK_LEVELS else "medium"
    # ⚠️ 无法判定的来源一律降级为 llm_inference：把推断冒充法条是本项目最不能接受的失败
    point["source_type"] = source if source in _SOURCE_TYPES else "llm_inference"
    point["description"] = str(raw.get("description") or "模型未给出说明")
    return point


def _point_columns(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_level": point["risk_level"],
        "risk_category": point.get("risk_category"),
        "clause_title": point.get("clause_title"),
        "clause_text": point.get("clause_text"),
        "char_start": point.get("char_start"),
        "char_end": point.get("char_end"),
        "description": point["description"],
        "suggestion": point.get("suggestion"),
        "legal_basis": point.get("legal_basis"),
        "source_type": point["source_type"],
        "confidence": point.get("confidence"),
    }


# ============================================================
# 阶段五：报告生成（M2-06）
# ============================================================


def _stage_report(db: Session, task: ReviewTask, ctx: _Context) -> None:
    counts = dict.fromkeys(_RISK_LEVELS, 0)
    for point in ctx.risk_points:
        counts[point["risk_level"]] += 1

    title = _contract_title(db, task)
    summary = _summary(counts)
    pdf = build_report_pdf(
        contract_title=title,
        summary=summary,
        counts=counts,
        extracted_terms=ctx.terms,
        risk_points=ctx.risk_points,
    )

    digest = sha256_of(pdf)
    storage = get_storage()
    object_key = object_key_for(digest)
    storage.put(object_key, pdf)

    file_object = FileObject(
        sha256=digest,
        storage_bucket=storage.bucket,
        object_key=object_key,
        original_name=f"{title}-审查报告.pdf",
        byte_size=len(pdf),
        mime_type="application/pdf",
        uploader_id=task.user_id,
    )
    db.add(file_object)
    db.flush()

    task.report = ReviewReport(
        review_task_id=task.id,
        file_object_id=file_object.id,
        format="pdf",
        summary=summary,
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
    )


def _summary(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return "本次审查未发现风险点。"
    return (
        f"本合同共发现 {total} 处风险，其中高风险 {counts['high']} 处、"
        f"中风险 {counts['medium']} 处、低风险 {counts['low']} 处。"
    )


def _contract_title(db: Session, task: ReviewTask) -> str:
    from app.models.contract import Contract

    if task.contract_id:
        contract = db.get(Contract, task.contract_id)
        if contract is not None:
            return contract.title
    return f"合同 #{task.contract_version_id or task.id}"
