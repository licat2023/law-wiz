"""请求追踪号（request_id）的一致性测试。

**为什么需要这一组**：request_id 的价值在于把「用户看到的响应」与
「服务端日志」关联起来。这个关联一旦断开，**功能看起来完全正常** ——
接口照常返回 200、响应体里也照常有 request_id，只有在真的需要排障时
才会发现查不到任何日志。这类缺陷不会被任何功能测试覆盖，
只有针对性的断言能防住。

历史：`get_request_id` 起初每次调用都生成新号，而它被调用两次
（中间件写日志与响应头、路由依赖写响应体），导致**响应体与响应头的号不同**。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_response_body_and_header_carry_same_request_id(client: TestClient) -> None:
    """响应体与响应头必须是**同一个** request_id。

    这是用户能提供、且日志里能查到的那一个。两者不一致 = 排障链条断开。
    """
    resp = client.get("/api/v1/health")

    header_id = resp.headers.get("X-Request-ID")
    body_id = resp.json()["request_id"]

    assert header_id, "响应头必须带 X-Request-ID"
    assert body_id, "响应体必须带 request_id"
    assert header_id == body_id, (
        f"响应头与响应体的 request_id 不一致：header={header_id} body={body_id}。"
        "用户凭响应体里的号将查不到日志。"
    )


def test_request_id_is_stable_across_calls_in_one_request() -> None:
    """同一请求内多次取号必须相同。

    **直接暴露根因**：`get_request_id` 若每次都新建一个号，本用例立即失败。
    用构造的 Request 对象而非 HTTP 往返 —— 这样失败时指向的就是取号逻辑本身，
    不会与路由、前缀、响应模型等无关因素混淆。
    """
    from starlette.requests import Request

    from app.api.deps import get_request_id

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)

    first = get_request_id(request)
    second = get_request_id(request)
    third = get_request_id(request)

    assert first == second == third, (
        f"同一请求内取到了多个不同的 request_id：{first!r} / {second!r} / {third!r}。"
        "中间件与路由依赖各调用一次，不一致会导致响应头与响应体的号不同。"
    )


def test_different_requests_get_different_request_ids(client: TestClient) -> None:
    """不同请求必须拿到不同的号（否则日志会把两条请求混在一起）。"""
    a = client.get("/api/v1/health").json()["request_id"]
    b = client.get("/api/v1/health").json()["request_id"]
    assert a != b


def test_error_response_uses_same_request_id_as_header(client: TestClient) -> None:
    """**失败**响应也必须与响应头一致。

    异常处理器读的是 `request.state`，而路由依赖此前每次新建 ——
    这会造成"成功响应带 B、失败响应带 A"的诡异现象，同一机制两种值。
    """
    resp = client.get("/api/v1/users/me")  # 无令牌 → 401

    assert resp.status_code == 401
    assert resp.headers.get("X-Request-ID") == resp.json()["request_id"]

    resp2 = client.get("/api/v1/definitely-not-a-route")  # 404
    assert resp2.headers.get("X-Request-ID") == resp2.json()["request_id"]


def test_response_falls_back_to_the_request_context() -> None:
    """忘记注入 `RequestId` 依赖时，响应体也不得是空串。

    这是**兜底**：路由漏注入不是"少一个字段"，而是用户凭响应体里的号
    查不到任何日志（参见本文件开头的历史说明）。中间件把号绑进 ContextVar 后，
    `ApiResponse` 的默认值就能取到它。
    """
    from app.core.context import bind_request_id, reset_request_id
    from app.core.errors import ApiResponse, ErrorCode

    assert ApiResponse.ok(None).request_id == "", "请求上下文之外应为空串"

    token = bind_request_id("req_abcdef01")
    try:
        assert ApiResponse.ok(None).request_id == "req_abcdef01"
        assert ApiResponse.fail(ErrorCode.INTERNAL_ERROR, "出错了").request_id == "req_abcdef01"
    finally:
        reset_request_id(token)

    assert ApiResponse.ok(None).request_id == "", "还原后不应再泄漏上一个请求的号"
