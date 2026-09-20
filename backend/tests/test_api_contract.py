"""统一响应体与错误码的契约测试。

这些用例的价值：**把《05-接口设计》§3 的约定变成可执行的断言**。
文档会漂移，测试不会 —— 一旦有人改了响应体形状，这里会红。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import ErrorCode, http_status_for


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
    assert http_status_for(ErrorCode.ACCESS_TOKEN_INVALID) == 401
    assert http_status_for(ErrorCode.FORBIDDEN) == 403
    assert http_status_for(ErrorCode.REVIEW_NOT_FOUND) == 404
    assert http_status_for(ErrorCode.PHONE_TAKEN) == 409
    assert http_status_for(ErrorCode.FILE_TOO_LARGE) == 413
    assert http_status_for(ErrorCode.UNSUPPORTED_FILE_TYPE) == 415
    assert http_status_for(ErrorCode.RATE_LIMITED) == 429
    assert http_status_for(ErrorCode.INTERNAL_ERROR) == 500
    assert http_status_for(ErrorCode.LLM_BAD_RESPONSE) == 502
    assert http_status_for(ErrorCode.LLM_UNAVAILABLE) == 503
