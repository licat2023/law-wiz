"""审查切片测试（M2 的 C 组）—— C-01 ~ C-06。

⚠️ 用 `e2e_client` 而非 `client`：审查是**异步且分阶段提交**的，
必须在「允许真实提交」的环境里跑，否则流水线的进度写不进库、
轮询读不到，测试会得到与生产不一致的结论。

⚠️ AI 能力用两种方式对待：
- **默认（stub）**：验证"AI 未接入时任务优雅失败"这条真实路径；
- **替代品（monkeypatch）**：验证"AI 可用时的完整成功链路"。

这正是文档里"能力可降级"给开发带来的好处 —— 不必等真实 AI 就能测通全流程。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ErrorCode
from app.infra import llm as llm_module

REVIEWS = "/api/v1/reviews"


def _auth_headers(client: TestClient, phone: str = "13800000021") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": "abc12345", "verify_code": "000000"},
    )
    resp = client.post("/api/v1/auth/login", json={"account": phone, "password": "abc12345"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _upload(client: TestClient, headers: dict[str, str], pdf: bytes) -> str:
    resp = client.post(
        "/api/v1/files",
        files={"file": ("采购合同.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["file_id"]


def _create_review(client: TestClient, headers: dict[str, str], file_id: str, **kwargs):
    key = kwargs.pop("key", "idem-key-1")
    return client.post(
        REVIEWS,
        json={"file_id": file_id, **kwargs},
        headers={**headers, "Idempotency-Key": key},
    )


def _fake_llm(system: str, user: str, schema: dict) -> dict:
    """替代品：按调用的 schema 形状返回不同结果。"""
    if "risk_points" in schema.get("properties", {}):
        return {
            "risk_points": [
                {
                    "risk_level": "high",
                    "risk_category": "legal",
                    "clause_title": "第八条 违约责任",
                    "clause_text": "违约金按合同总额的 30% 计算。",
                    "char_start": 10,
                    "char_end": 30,
                    "description": "违约金比例过高，可能被法院调减。",
                    "suggestion": "建议调整为合同总额的 10%–20%。",
                    "legal_basis": "《中华人民共和国民法典》第五百八十五条",
                    "source_type": "retrieved_law",
                    "confidence": 0.86,
                },
                {
                    "risk_level": "medium",
                    "description": "付款条件与验收标准未约定明确。",
                    # ⚠️ 故意给一个**非法**来源，用于验证规范化逻辑
                    "source_type": "我就这么认为",
                },
            ]
        }
    return {
        "parties": ["甲方：甲公司", "乙方：乙公司"],
        "amount": "人民币 120 万元",
        "liability": "违约金按合同总额的 30% 计算",
    }


# ============================================================
# C-01 发起审查
# ============================================================


def test_create_review_requires_idempotency_key(e2e_client, sample_pdf) -> None:
    """§3.5 规定该头**必填**，缺失即 40001。"""
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    resp = e2e_client.post(REVIEWS, json={"file_id": file_id}, headers=headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


def test_review_returns_202_with_task_id(e2e_client, sample_pdf, monkeypatch) -> None:
    """接口**立即返回**任务号，不在请求内完成审查（03-概要设计 §5.1）。"""
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    resp = _create_review(e2e_client, headers, file_id)

    assert resp.status_code == 202
    data = resp.json()["data"]
    assert isinstance(data["task_id"], str)
    assert data["status"] == "pending"
    assert data["progress"] == 0


def test_idempotency_key_returns_the_same_task(e2e_client, sample_pdf, monkeypatch) -> None:
    """同一 key 重复提交返回首次结果，而不是再建一个任务。

    注意与 `40905` 的区别：这里**不靠**"同文件正在审查"的兜底，
    靠的是幂等缓存本身 —— 两者是独立的防线。
    """
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    first = _create_review(e2e_client, headers, file_id, key="same-key")
    second = _create_review(e2e_client, headers, file_id, key="same-key")

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]


def test_duplicate_review_of_same_file_is_40905(e2e_client, sample_pdf, monkeypatch) -> None:
    """默认拒绝同一文件的并发审查；`force=true` 才允许。"""
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    assert _create_review(e2e_client, headers, file_id, key="k1").status_code == 202

    duplicate = _create_review(e2e_client, headers, file_id, key="k2")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == int(ErrorCode.REVIEW_IN_PROGRESS)

    forced = _create_review(e2e_client, headers, file_id, key="k3", force=True)
    assert forced.status_code == 202


# ============================================================
# 流水线：AI 未接入 / AI 可用
# ============================================================


def test_review_fails_gracefully_when_llm_not_configured(e2e_client, sample_pdf) -> None:
    """**AI 未接入时任务优雅失败** —— 不是卡住、不是 5xx，而是可解释的失败状态。

    这条路径现在就能测，正是"能力可降级"设计的意义：不必等真实 AI 落地，
    就能确认失败会被正确记录并可通过 C-02 看到。
    """
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    created = _create_review(e2e_client, headers, file_id)
    assert created.status_code == 202
    task_id = created.json()["data"]["task_id"]

    # TestClient 会在响应返回后同步执行后台任务，因此此刻任务已结束
    task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]

    assert task["status"] == "failed"
    assert task["error_code"] == str(int(ErrorCode.LLM_UNAVAILABLE))
    assert task["error_message"], "失败必须带面向用户的说明"
    assert task["finished_at"]


def test_full_flow_with_fake_llm(e2e_client, sample_pdf, monkeypatch) -> None:
    """AI 可用时的完整链路：上传 → 审查 → 结果 → 报告。"""
    monkeypatch.setattr(llm_module, "complete_structured", _fake_llm)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    created = _create_review(e2e_client, headers, file_id)
    task_id = created.json()["data"]["task_id"]

    task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]
    assert task["status"] == "succeeded"
    assert task["progress"] == 100
    assert task["stage"] is None
    assert task["error_code"] is None

    # --- C-03 结果 ---
    result = e2e_client.get(f"{REVIEWS}/{task_id}/result", headers=headers).json()["data"]
    assert result["counts"] == {"high": 1, "medium": 1, "low": 0}
    assert result["extracted_terms"]["amount"] == "人民币 120 万元"
    assert result["contract_title"] == "采购合同.pdf"
    assert len(result["risk_points"]) == 2

    high = result["risk_points"][0]
    assert high["risk_level"] == "high"
    assert high["source_type"] == "retrieved_law"
    assert high["char_start"] == 10

    # ⚠️ 非法 source_type 必须降级为 llm_inference —— 绝不能把推断冒充成法条
    assert result["risk_points"][1]["source_type"] == "llm_inference"

    # --- C-04 报告 ---
    report = e2e_client.get(f"{REVIEWS}/{task_id}/report", headers=headers)
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF-"), "报告必须是合法 PDF"
    assert "filename*=UTF-8''" in report.headers["content-disposition"], "中文文件名需 RFC 5987 编码"


# ============================================================
# C-02 / C-03 的状态门槛
# ============================================================


def test_result_before_finish_is_40906(e2e_client, sample_pdf, monkeypatch) -> None:
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    resp = e2e_client.get(f"{REVIEWS}/{task_id}/result", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.REVIEW_NOT_FINISHED)


def test_result_of_failed_task_is_40907(e2e_client, sample_pdf) -> None:
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    resp = e2e_client.get(f"{REVIEWS}/{task_id}/result", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.REVIEW_FAILED)


def test_missing_file_content_fails_with_actionable_message(e2e_client, sample_pdf, _temp_storage) -> None:
    """数据库有记录、对象存储缺内容时，失败信息必须**可操作**。

    这不是假想场景：人为清理、迁移未同步、对象存储丢数据都会造成两边不一致。
    任务仍应优雅失败，而不是抛 500；且要告诉用户**该做什么**。
    """
    import shutil

    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    shutil.rmtree(_temp_storage._root, ignore_errors=True)  # 模拟对象存储丢内容

    created = _create_review(e2e_client, headers, file_id)
    assert created.status_code == 202
    task_id = created.json()["data"]["task_id"]

    task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]

    assert task["status"] == "failed"
    assert task["error_code"] == str(int(ErrorCode.FILE_NOT_FOUND))
    assert "重新上传" in task["error_message"], "失败信息应包含可操作的指引"


def test_pdf_over_page_limit_fails_task_with_actionable_message(e2e_client, make_pdf, monkeypatch) -> None:
    """页数超限的 PDF 必须让任务**优雅失败**，而不是把进程内存吃干。

    上限由解析层兜住（上传侧只限制 20 MB，管不住页数）。
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_pdf_pages", 1)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, make_pdf(["第一页", "第二页"]))

    created = _create_review(e2e_client, headers, file_id)
    assert created.status_code == 202
    task_id = created.json()["data"]["task_id"]

    task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]

    assert task["status"] == "failed"
    assert task["error_code"] == str(int(ErrorCode.PARAM_INVALID))
    assert "页" in task["error_message"], "失败信息应说明是页数问题"


# ============================================================
# 越权与不存在
# ============================================================


def test_other_user_cannot_read_task(e2e_client, sample_pdf, monkeypatch) -> None:
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    owner = _auth_headers(e2e_client, phone="13800000021")
    file_id = _upload(e2e_client, owner, sample_pdf)
    task_id = _create_review(e2e_client, owner, file_id).json()["data"]["task_id"]

    intruder = _auth_headers(e2e_client, phone="13800000022")
    resp = e2e_client.get(f"{REVIEWS}/{task_id}", headers=intruder)

    assert resp.status_code == 403
    assert resp.json()["code"] == int(ErrorCode.FORBIDDEN)


def test_missing_task_is_40401(e2e_client) -> None:
    headers = _auth_headers(e2e_client)

    resp = e2e_client.get(f"{REVIEWS}/99999999", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.REVIEW_NOT_FOUND)


def test_create_review_rejects_unknown_file(e2e_client) -> None:
    headers = _auth_headers(e2e_client)

    resp = _create_review(e2e_client, headers, "99999999")

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.FILE_NOT_FOUND)


def test_another_user_can_review_the_same_content(e2e_client, sample_pdf, monkeypatch) -> None:
    """**同一份内容被第二个用户审查时必须可用。**

    背景（这是联调中真实撞到的问题）：内容寻址是**全局去重**的 —— 第二个用户
    上传同一份合同会拿到**同一个** `file_object`（`uploader_id` 仍是第一个上传者）。
    若 C-01 按 `uploader_id` 鉴权，用户就**无法审查自己刚上传的文件**。

    `uploader_id` 的语义是"谁**最先**上传了这个内容"，**不代表文件属于他**
    （`docs/04 §5.1`）；且 C-01 的契约错误码里本就没有 `40301`
    （见 `docs/05 §5.4`）。归属由 `review_task.user_id` / `contract.owner_id` 保证。
    """
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)

    first = _auth_headers(e2e_client, phone="13800000021")
    first_file_id = _upload(e2e_client, first, sample_pdf)

    second = _auth_headers(e2e_client, phone="13800000022")
    again = e2e_client.post(
        "/api/v1/files",
        files={"file": ("我自己传的副本.pdf", sample_pdf, "application/pdf")},
        headers=second,
    )
    second_file_id = again.json()["data"]["file_id"]

    assert second_file_id == first_file_id, "同一内容应命中去重，复用同一个 file_object"
    assert again.json()["data"]["is_duplicate"] is True

    resp = _create_review(e2e_client, second, second_file_id)

    assert resp.status_code == 202, f"第二个用户必须能审查这份内容，实际：{resp.text}"
    # 审查任务归属于**发起者**，而不是文件的首个上传者
    task_id = resp.json()["data"]["task_id"]
    mine = e2e_client.get(f"{REVIEWS}/{task_id}", headers=second)
    assert mine.json()["code"] == 0
    theirs = e2e_client.get(f"{REVIEWS}/{task_id}", headers=first)
    assert theirs.json()["code"] == int(ErrorCode.FORBIDDEN), "首个上传者无权查看他人发起的任务"


# ============================================================
# C-05 历史列表
# ============================================================


def test_list_reviews_paginates_and_filters(e2e_client, sample_pdf, monkeypatch) -> None:
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    for index in range(3):
        _create_review(e2e_client, headers, file_id, key=f"list-{index}", force=True)

    page = e2e_client.get(f"{REVIEWS}?page=1&page_size=2", headers=headers).json()["data"]
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["page"] == 1 and page["page_size"] == 2

    pending = e2e_client.get(f"{REVIEWS}?status=pending", headers=headers).json()["data"]
    assert pending["total"] == 3

    finished = e2e_client.get(f"{REVIEWS}?status=succeeded", headers=headers).json()["data"]
    assert finished["total"] == 0


def test_list_reviews_rejects_bad_pagination(e2e_client) -> None:
    headers = _auth_headers(e2e_client)

    resp = e2e_client.get(f"{REVIEWS}?page_size=9999", headers=headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PAGE_OUT_OF_RANGE)


def test_list_reviews_rejects_bad_sort(e2e_client) -> None:
    headers = _auth_headers(e2e_client)

    resp = e2e_client.get(f"{REVIEWS}?sort=drop-table", headers=headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


# ============================================================
# C-06 标记误报
# ============================================================


def test_dismiss_risk_point(e2e_client, sample_pdf, monkeypatch) -> None:
    """**这是收集模型误报样本的唯一途径**，必须可用（04-数据库设计 §5.7）。"""
    monkeypatch.setattr(llm_module, "complete_structured", _fake_llm)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    result = e2e_client.get(f"{REVIEWS}/{task_id}/result", headers=headers).json()["data"]
    point_id = result["risk_points"][0]["id"]
    assert result["risk_points"][0]["is_dismissed"] is False

    resp = e2e_client.patch(
        f"{REVIEWS}/{task_id}/risk-points/{point_id}",
        json={"is_dismissed": True},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["is_dismissed"] is True

    refreshed = e2e_client.get(f"{REVIEWS}/{task_id}/result", headers=headers).json()["data"]
    assert refreshed["risk_points"][0]["is_dismissed"] is True


def test_dismiss_rejects_point_of_other_task(e2e_client, sample_pdf, monkeypatch) -> None:
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    resp = e2e_client.patch(
        f"{REVIEWS}/{task_id}/risk-points/99999999",
        json={"is_dismissed": True},
        headers=headers,
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.REVIEW_NOT_FOUND)


@pytest.mark.parametrize("body", [{}, {"is_dismissed": "not-a-bool"}])
def test_dismiss_validates_body(e2e_client, sample_pdf, monkeypatch, body) -> None:
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    resp = e2e_client.patch(f"{REVIEWS}/{task_id}/risk-points/1", json=body, headers=headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


# ============================================================
# 并发闸门（app/infra/concurrency.py）
# ============================================================


async def test_pipeline_fails_task_when_concurrency_is_full(e2e_client, sample_pdf, monkeypatch) -> None:
    """并发已满时，任务必须以**明确原因**失败。

    为什么这样取舍：让它**失败得清楚**（`42901` + 可读消息），
    而不是无限期挂在 `pending`（用户无从判断）或继续占着线程等下去
    （那就等于没做并发限制）。
    """
    from app.infra.concurrency import PipelineGate
    from app.slices.review import pipeline as review_pipeline

    busy = PipelineGate(max_concurrent=1, timeout_seconds=0.05)
    assert await busy.acquire(), "先占满唯一的槽位"
    monkeypatch.setattr(review_pipeline, "pipeline_gate", busy)

    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)
    task_id = _create_review(e2e_client, headers, file_id).json()["data"]["task_id"]

    task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]

    assert task["status"] == "failed"
    assert task["error_code"] == str(int(ErrorCode.RATE_LIMITED))
    assert "繁忙" in task["error_message"], f"失败原因应可读：{task['error_message']}"


async def test_gate_is_released_after_pipeline_finishes(e2e_client, sample_pdf) -> None:
    """流水线结束后必须释放槽位 —— 否则跑几次就把并发能力用光了。

    闸门自带占用计数，释放多于占用会直接抛错，
    所以本用例也能顺带发现"少 release 或多 release"的问题。
    """
    from app.infra.concurrency import pipeline_gate

    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    for index in range(3):
        resp = _create_review(e2e_client, headers, file_id, key=f"gate-{index}", force=True)
        assert resp.status_code == 202, resp.text
        task_id = resp.json()["data"]["task_id"]
        task = e2e_client.get(f"{REVIEWS}/{task_id}", headers=headers).json()["data"]
        # 默认 stub 提供方 → 流水线会失败，但**必须已经跑完并释放槽位**
        assert task["status"] in ("succeeded", "failed"), task

    assert await pipeline_gate.acquire(0.1), "连续跑完三次后槽位应已全部归还"
    pipeline_gate.release()


def test_report_format_is_validated(client: TestClient) -> None:
    """C-04 的 `format` 查询参数必须被校验（05-接口设计 §5.4：一期仅支持 pdf）。

    参数校验发生在业务逻辑之前，因此不需要先造出一个已完成的任务。
    """
    headers = _auth_headers(client)

    bad = client.get(f"{REVIEWS}/99999999/report?format=html", headers=headers)
    assert bad.status_code == 400
    assert bad.json()["code"] == int(ErrorCode.PARAM_INVALID)

    # 合法取值应继续走业务逻辑：任务不存在 → 40401（而不是参数错误）
    ok = client.get(f"{REVIEWS}/99999999/report?format=pdf", headers=headers)
    assert ok.json()["code"] == int(ErrorCode.REVIEW_NOT_FOUND)


def test_idempotency_key_is_scoped_per_endpoint(
    e2e_client, sample_pdf, _memory_idempotency_store: dict[str, dict]
) -> None:
    """幂等键必须**按接口作用域**存储。

    客户端可能在两个接口上复用同一个 key。若不隔离，后一个接口会把
    **前一个接口的响应体**原样返回，前端拿到形状不符的数据。
    """
    headers = _auth_headers(e2e_client)
    file_id = _upload(e2e_client, headers, sample_pdf)

    assert _create_review(e2e_client, headers, file_id, key="reused-key").status_code == 202

    assert any(key.startswith("review:") for key in _memory_idempotency_store), (
        f"键应带接口作用域，实际存的是：{list(_memory_idempotency_store)}"
    )
