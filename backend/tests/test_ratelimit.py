"""限流的契约测试（05-接口设计 §4.5）。

⚠️ 阈值与窗口逻辑走**真实实现**（只有 `_incr` 被替换成内存字典），
因此这些用例验证的是"生产会怎么限流"，而不是替身自身的行为。
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ErrorCode

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/users/me"
REVIEWS = "/api/v1/reviews"


def _auth(client: TestClient, phone: str = "13800000061") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": "abc12345", "verify_code": "000000"},
    )
    resp = client.post(LOGIN, json={"account": phone, "password": "abc12345"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


# ============================================================
# 阈值与响应头
# ============================================================


def test_auth_is_limited_per_ip(client: TestClient) -> None:
    """认证类 10 次/分/IP —— 第 11 次必须被挡，并带齐 §4.5 要求的响应头。"""
    for _ in range(10):
        resp = client.post(LOGIN, json={"account": "19900000000", "password": "abc12345"})
        assert resp.json()["code"] != int(ErrorCode.RATE_LIMITED), "前 10 次不应被限流"

    blocked = client.post(LOGIN, json={"account": "19900000000", "password": "abc12345"})

    assert blocked.status_code == 429
    assert blocked.json()["code"] == int(ErrorCode.RATE_LIMITED)
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["X-RateLimit-Limit"] == "10"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert int(blocked.headers["X-RateLimit-Reset"]) > int(time.time()) - 120


def test_successful_response_carries_rate_limit_headers(client: TestClient) -> None:
    """2xx 响应顺带带上限流头，前端可据此提示剩余额度。

    ⚠️ 文档（§4.5）只要求**限流响应（429）**必须带这组头 —— 见
    `test_auth_is_limited_per_ip`。**业务失败响应不带**：异常处理器构造的是新响应，
    依赖设置的头会丢失，而文档并未要求该场景带。此处不额外扩展。
    """
    headers = _auth(client)
    resp = client.get(ME, headers=headers)

    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == str(get_settings().rate_limit_read_per_minute)
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers


def test_limit_comes_from_settings(client: TestClient, monkeypatch) -> None:
    """阈值来自配置，部署时按容量调整即可，不必改代码。"""
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 2)

    for _ in range(2):
        resp = client.post(LOGIN, json={"account": "x", "password": "y"})
        assert resp.json()["code"] != int(ErrorCode.RATE_LIMITED)

    blocked = client.post(LOGIN, json={"account": "x", "password": "y"})
    assert blocked.json()["code"] == int(ErrorCode.RATE_LIMITED)
    assert blocked.headers["X-RateLimit-Limit"] == "2"


# ============================================================
# 分档：各类别互不影响，且计数主体正确
# ============================================================


def test_auth_and_read_use_separate_buckets(
    client: TestClient, _memory_rate_limit_store: dict[str, int]
) -> None:
    """认证类与查询类必须是**各自独立的桶** —— 否则打满登录会连带封掉查询。"""
    headers = _auth(client)
    client.get(ME, headers=headers)

    keys = list(_memory_rate_limit_store)
    assert any(":rl:auth:" in key for key in keys), f"应有 auth 桶，实际 {keys}"
    assert any(":rl:read:" in key for key in keys), f"应有 read 桶，实际 {keys}"


def test_auth_bucket_keyed_by_ip(client: TestClient, _memory_rate_limit_store: dict[str, int]) -> None:
    """认证类按 **IP** 计数 —— 此时还没有用户身份（登录本身就在这一步）。"""
    client.post(LOGIN, json={"account": "19900000002", "password": "abc12345"})

    subjects = [key.split(":rl:auth:")[1] for key in _memory_rate_limit_store if ":rl:auth:" in key]
    assert subjects, "应产生 auth 计数"
    assert all(subject.startswith("ip") for subject in subjects), f"应以 ip 为主体：{subjects}"


def test_ai_bucket_keyed_by_user_and_blocks(
    e2e_client, sample_pdf, monkeypatch, _memory_rate_limit_store: dict[str, int]
) -> None:
    """AI 类按**用户**计数并生效（阈值调小以少发请求）。"""
    from app.slices.review import service

    monkeypatch.setattr(service, "enqueue", lambda task_id: None)
    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 2)

    headers = _auth(e2e_client, phone="13800000062")
    upload = e2e_client.post(
        "/api/v1/files",
        files={"file": ("rl.pdf", sample_pdf, "application/pdf")},
        headers=headers,
    )
    file_id = upload.json()["data"]["file_id"]

    for index in range(2):
        resp = e2e_client.post(
            REVIEWS,
            json={"file_id": file_id, "force": True},
            headers={**headers, "Idempotency-Key": f"rl-{index}"},
        )
        assert resp.status_code == 202, resp.text

    blocked = e2e_client.post(
        REVIEWS,
        json={"file_id": file_id, "force": True},
        headers={**headers, "Idempotency-Key": "rl-blocked"},
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == int(ErrorCode.RATE_LIMITED)
    assert blocked.headers["X-RateLimit-Limit"] == "2"

    subjects = [key.split(":rl:ai:")[1] for key in _memory_rate_limit_store if ":rl:ai:" in key]
    assert subjects and all(subject.startswith("u") for subject in subjects), f"应以用户为主体：{subjects}"


# ============================================================
# 降级与运维性质
# ============================================================


def test_redis_unavailable_degrades_to_allow(client: TestClient, monkeypatch) -> None:
    """Redis 挂了要**放行**并告警，而不是让全站 429 —— 限流是保护措施，不该成为可用性依赖。"""
    from app.infra import ratelimit

    monkeypatch.setattr(ratelimit, "_incr", lambda key, ttl: None)

    for _ in range(15):
        resp = client.post(LOGIN, json={"account": "19900000003", "password": "abc12345"})
        assert resp.json()["code"] != int(ErrorCode.RATE_LIMITED)


def test_counter_key_carries_ttl_and_window(monkeypatch) -> None:
    """计数键必须带 TTL 且**按窗口分段**，否则键会永久堆积（Redis 内存泄漏）。"""
    calls: list[tuple[str, int]] = []

    from app.infra import ratelimit

    def spy(key: str, ttl: int) -> int:
        calls.append((key, ttl))
        return 1

    monkeypatch.setattr(ratelimit, "_incr", spy)
    ratelimit.hit("auth", "ip1.2.3.4", 10)

    assert calls, "应调用 _incr"
    key, ttl = calls[0]
    assert ttl >= ratelimit.WINDOW_SECONDS, f"TTL 不应短于窗口：{ttl}"
    assert ":rl:auth:ip1.2.3.4:" in key, f"键形状不符：{key}"
    expected_window = str(int(time.time()) // ratelimit.WINDOW_SECONDS)
    assert key.endswith(expected_window), f"键应按窗口分段：{key}"
