"""统一响应体与错误码的契约测试。

这些用例的价值：**把《05-接口设计》§3 的约定变成可执行的断言**。
文档会漂移，测试不会 —— 一旦有人改了响应体形状，这里会红。
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ErrorCode, http_status_for

# 契约要求的时间形状：ISO 8601 **带时区偏移**、毫秒（05-接口设计 §3）
_ISO_WITH_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+08:00$")


def test_health_returns_envelope(client: TestClient) -> None:
    """F-01：健康检查返回统一响应体。"""
    resp = client.get("/api/v1/health")
    body = resp.json()

    assert set(body) == {"code", "message", "data", "request_id"}, "响应体形状必须固定为四字段"
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["request_id"], "每个响应都必须带 request_id"


def test_health_reports_runtime_for_self_check(client: TestClient) -> None:
    """F-01：必须暴露运行环境，供部署后自查用的是哪个解释器（ADR-0009）。"""
    data = client.get("/api/v1/health").json()["data"]

    assert "runtime" in data
    runtime = data["runtime"]
    assert runtime["python"].startswith("3.14"), f"期望 Python 3.14，实际 {runtime['python']}"
    assert runtime["free_threading"] is False, "测试环境必须是有 GIL 的标准构建"
    assert runtime["implementation"] == "cpython"


def test_request_id_header_present(client: TestClient) -> None:
    """request_id 同时出现在响应头，便于用户报障时直接提供。"""
    resp = client.get("/api/v1/health")
    assert resp.headers.get("X-Request-ID")


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    """404 也必须是统一响应体 —— 否则前端要写两套解析逻辑。"""
    resp = client.get("/api/v1/definitely-not-a-route")
    body = resp.json()

    assert resp.status_code == 404
    assert set(body) == {"code", "message", "data", "request_id"}
    assert body["code"] != 0


def test_unknown_route_uses_the_generic_404_code(client: TestClient) -> None:
    """未匹配路由必须是 `40400`（资源不存在），**不能**复用某个资源的专属码。

    若复用 `40401`（审查任务不存在），前端在"任务详情页"之外的场景收到它时
    会给出与上下文无关的提示；排查时也会误以为审查模块出了问题。
    """
    body = client.get("/api/v1/definitely-not-a-route").json()
    assert body["code"] == int(ErrorCode.RESOURCE_NOT_FOUND)


def test_method_not_allowed_keeps_its_own_code(client: TestClient) -> None:
    """方法与路径不匹配是 40500 + HTTP 405。

    ⚠️ 不能落到 `50000`：前端以 `code` 为准，会把"用错方法"显示成
    "服务器内部错误"，把客户端问题伪装成服务端故障。
    """
    resp = client.post("/api/v1/health")  # /health 只允许 GET

    assert resp.status_code == 405
    assert resp.json()["code"] == int(ErrorCode.METHOD_NOT_ALLOWED)


def test_malformed_json_has_its_own_code(client: TestClient) -> None:
    """JSON 解析失败是 `40002`，与字段校验失败（`40001`）区分（05-接口设计 §3.3）。

    FastAPI 会把 `JSONDecodeError` 也包成 `RequestValidationError`，
    若不显式分流，畸形的请求体会被报成"字段格式不正确"。
    """
    resp = client.post(
        "/api/v1/auth/login",
        content='{"account": "13800000001", ',
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.BODY_MALFORMED)


def test_validation_error_uses_field_level_details(client: TestClient) -> None:
    """参数校验失败必须给**字段级**原因，前端才能高亮具体表单项。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"phone": "138", "password": "short", "verify_code": "000000"},
    )
    body = resp.json()

    assert resp.status_code == 400
    assert body["code"] == int(ErrorCode.PARAM_INVALID)
    details = body["data"]["details"]
    assert isinstance(details, list) and details, "必须给出字段级错误"

    fields = {d["field"] for d in details}
    # field 不应带 body./query. 前缀，否则前端无法与表单字段对应
    assert "phone" in fields
    assert not any(f.startswith(("body", "query", "path")) for f in fields), f"字段名不应带位置前缀：{fields}"


def test_error_code_to_http_status_mapping() -> None:
    """错误码段 → HTTP 状态码的映射必须与《05》§3.3 一致。"""
    assert http_status_for(ErrorCode.PARAM_INVALID) == 400
    assert http_status_for(ErrorCode.BODY_MALFORMED) == 400
    assert http_status_for(ErrorCode.ACCESS_TOKEN_INVALID) == 401
    assert http_status_for(ErrorCode.FORBIDDEN) == 403
    assert http_status_for(ErrorCode.RESOURCE_NOT_FOUND) == 404
    assert http_status_for(ErrorCode.REVIEW_NOT_FOUND) == 404
    assert http_status_for(ErrorCode.METHOD_NOT_ALLOWED) == 405
    assert http_status_for(ErrorCode.PHONE_TAKEN) == 409
    assert http_status_for(ErrorCode.FILE_TOO_LARGE) == 413
    assert http_status_for(ErrorCode.UNSUPPORTED_FILE_TYPE) == 415
    assert http_status_for(ErrorCode.RATE_LIMITED) == 429
    assert http_status_for(ErrorCode.INTERNAL_ERROR) == 500
    assert http_status_for(ErrorCode.LLM_BAD_RESPONSE) == 502
    assert http_status_for(ErrorCode.LLM_UNAVAILABLE) == 503


# ============================================================
# 时间格式（05-接口设计 §3）
# ============================================================


def test_to_iso_produces_offset_and_milliseconds() -> None:
    """`to_iso` 是**所有切片唯一的时间序列化出口**，行为必须符合契约。

    为什么专门测它：不带时区偏移的时间串会被 `new Date()` 按**浏览器本地时区**
    解释 —— 时区不是 +08:00 的机器上时间就显示错了。而且这类缺陷不会被任何
    "功能能否跑通"的测试覆盖，只能靠形状断言。
    """
    from app.core.clock import to_iso

    assert to_iso(None) is None

    # 库里存的是 naive 的北京时间 → 补上 +08:00
    assert to_iso(dt.datetime(2026, 9, 20, 15, 58, 19, 637006)) == ("2026-09-20T15:58:19.637+08:00")
    # 微秒截断为毫秒（与 DATETIME(3) 精度一致）
    assert to_iso(dt.datetime(2026, 9, 20, 15, 58, 19, 123999)).endswith(".123+08:00")
    # 已带时区的保持其自身偏移，不被改写成 +08:00
    assert to_iso(dt.datetime(2026, 9, 20, 15, 58, 19, tzinfo=dt.UTC)) == ("2026-09-20T15:58:19.000+00:00")


def test_api_time_fields_match_the_contract_format(client: TestClient) -> None:
    """端到端确认各接口返回的时间串符合契约形状。

    覆盖两条不同的产生路径：`/health` 由 Python 直接生成，
    `/users/me` 由数据库 `DATETIME(3)` 读回 —— 两条都必须带偏移。
    """
    health = client.get("/api/v1/health").json()["data"]
    assert _ISO_WITH_OFFSET.match(health["checked_at"]), health["checked_at"]
    assert _ISO_WITH_OFFSET.match(health["runtime"]["started_at"]), health["runtime"]["started_at"]

    client.post(
        "/api/v1/auth/register",
        json={"phone": "13800000077", "password": "abc12345", "verify_code": "000000"},
    )
    login = client.post("/api/v1/auth/login", json={"account": "13800000077", "password": "abc12345"}).json()[
        "data"
    ]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {login['access_token']}"}).json()[
        "data"
    ]

    assert _ISO_WITH_OFFSET.match(me["created_at"]), me["created_at"]
    assert _ISO_WITH_OFFSET.match(me["last_login_at"]), me["last_login_at"]


# ============================================================
# 请求体大小与字段长度上限
# ============================================================


def test_oversized_json_body_is_rejected_before_parsing(client: TestClient) -> None:
    """超大 JSON 请求体必须在**解析之前**被拒。

    ⚠️ 这一层不能用字段级 `max_length` 替代：字段校验发生在请求体**完整解析之后**，
    届时内存已经被吃掉了。所以这里验证的是中间件层。
    """
    from app.api.middleware import _MAX_JSON_BODY_BYTES

    resp = client.post(
        "/api/v1/auth/login",
        content="x" * (_MAX_JSON_BODY_BYTES + 1024),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 413, resp.text[:200]
    body = resp.json()
    assert body["code"] == int(ErrorCode.FILE_TOO_LARGE)
    assert set(body) == {"code", "message", "data", "request_id"}, "仍是统一响应体"


def test_rejected_body_still_carries_matching_request_id(client: TestClient) -> None:
    """被中间件拒掉时，响应头与响应体仍是**同一个** request_id（与访问日志同源）。"""
    from app.api.middleware import _MAX_JSON_BODY_BYTES

    resp = client.post(
        "/api/v1/auth/login",
        content="x" * (_MAX_JSON_BODY_BYTES + 1024),
        headers={"Content-Type": "application/json"},
    )

    assert resp.headers.get("X-Request-ID") == resp.json()["request_id"]


def test_multipart_and_json_have_different_limits() -> None:
    """上传是 multipart，**不能**套用 JSON 的上限 —— 否则 20 MB 的文件传不上来。"""
    from app.api.middleware import (
        _MAX_JSON_BODY_BYTES,
        _MULTIPART_OVERHEAD_BYTES,
        _body_limit,
    )
    from app.core.config import get_settings

    json_limit = _body_limit("application/json")
    multipart_limit = _body_limit("multipart/form-data; boundary=xyz")

    assert json_limit == _MAX_JSON_BODY_BYTES
    assert multipart_limit == get_settings().max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
    assert multipart_limit > json_limit, "上传上限必须大于 JSON 上限，否则大文件会被误拒"


def test_oversized_kb_content_is_rejected_at_field_level() -> None:
    """字段级上限：kb 语料的 content（50 万字符）。"""
    from app.slices.kb.schemas import CreateDocumentRequest

    with pytest.raises(Exception) as excinfo:
        CreateDocumentRequest(doc_type="law", title="超长语料", content="x" * 500_001)

    assert "content" in str(excinfo.value)


def test_refresh_token_length_is_bounded(client: TestClient) -> None:
    """令牌长度必须受限 —— 不设上限等于允许客户端提交任意长字符串。"""
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "t" * 5000})

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)
    fields = {detail["field"] for detail in resp.json()["data"]["details"]}
    assert "refresh_token" in fields


def test_review_file_id_length_is_bounded(client: TestClient, registered_user: dict[str, str]) -> None:
    """`file_id` 是 BIGINT 的字符串形式，不该接受任意长输入。"""
    resp = client.post(
        "/api/v1/reviews",
        json={"file_id": "9" * 100},
        headers={
            "Authorization": f"Bearer {registered_user['access_token']}",
            "Idempotency-Key": "length-check",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)
