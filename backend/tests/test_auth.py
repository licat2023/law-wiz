"""认证切片测试（M1，P1）—— 端到端参考实现。

这些用例覆盖《05-接口设计》§5.2 的 A-01 ~ A-06，以及三条容易被做错的安全约定：
1. 登录失败**不区分**"账号不存在"与"密码错误"（防账号枚举）；
2. 手机号与邮箱**脱敏返回**；
3. 刷新令牌**轮换**，旧令牌立即失效。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import ErrorCode

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/users/me"


def _register(client: TestClient, **over: object):
    payload = {"phone": "13800000002", "password": "abc12345", "verify_code": "000000"}
    payload.update(over)
    return client.post(REGISTER, json=payload)


# ============================================================
# A-01 注册
# ============================================================


def test_register_success(client: TestClient) -> None:
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 0
    # ID 必须是字符串（05-接口设计 §3.4），否则前端 JS 在大 ID 上会丢精度
    assert isinstance(body["data"]["user_id"], str)


def test_register_duplicate_phone_is_40901(client: TestClient) -> None:
    assert _register(client).status_code == 201
    resp = _register(client)
    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.PHONE_TAKEN)


def test_register_duplicate_email_is_40902(client: TestClient) -> None:
    assert _register(client, phone=None, email="a@b.com").status_code == 201
    resp = _register(client, phone=None, email="a@b.com")
    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.EMAIL_TAKEN)


def test_register_requires_at_least_one_identity(client: TestClient) -> None:
    """phone 与 email 至少提供一个（05-接口设计 §5.2）。"""
    resp = _register(client, phone=None, email=None)
    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


def test_register_rejects_bad_phone(client: TestClient) -> None:
    resp = _register(client, phone="12345")
    assert resp.status_code == 400
    fields = {d["field"] for d in resp.json()["data"]["details"]}
    assert "phone" in fields


def test_register_rejects_weak_password(client: TestClient) -> None:
    """密码需同时含字母与数字。"""
    resp = _register(client, password="12345678")
    assert resp.status_code == 400
    fields = {d["field"] for d in resp.json()["data"]["details"]}
    assert "password" in fields


def test_register_rejects_wrong_verify_code(client: TestClient) -> None:
    resp = _register(client, verify_code="999999")
    assert resp.status_code == 400
    fields = {d["field"] for d in resp.json()["data"]["details"]}
    assert "verify_code" in fields


# ============================================================
# A-02 登录
# ============================================================


def test_login_success_returns_both_tokens(client: TestClient) -> None:
    _register(client)
    resp = client.post(LOGIN, json={"account": "13800000002", "password": "abc12345"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 1800


def test_login_with_email_also_works(client: TestClient) -> None:
    _register(client, phone=None, email="u@example.com")
    resp = client.post(LOGIN, json={"account": "u@example.com", "password": "abc12345"})
    assert resp.status_code == 200


def test_login_wrong_password_and_unknown_account_are_indistinguishable(
    client: TestClient,
) -> None:
    """**防账号枚举**：两种失败必须返回同一个错误码。

    若区分开，攻击者就能用登录接口探测哪些手机号已注册 ——
    这本身就是一次用户信息泄露（05-接口设计 §5.2）。
    """
    _register(client, phone="13800000003")

    wrong_pw = client.post(LOGIN, json={"account": "13800000003", "password": "wrong12345"})
    no_such = client.post(LOGIN, json={"account": "13900000000", "password": "wrong12345"})

    assert wrong_pw.status_code == no_such.status_code == 409
    assert wrong_pw.json()["code"] == no_such.json()["code"] == int(ErrorCode.BAD_CREDENTIALS)
    assert wrong_pw.json()["message"] == no_such.json()["message"]


# ============================================================
# A-03 / A-04 刷新与登出
# ============================================================


def test_refresh_rotates_token_and_invalidates_old(client: TestClient) -> None:
    """刷新令牌**轮换**：旧令牌用一次即失效（05-接口设计 §4.2）。"""
    _register(client)
    login = client.post(LOGIN, json={"account": "13800000002", "password": "abc12345"}).json()["data"]
    old_refresh = login["refresh_token"]

    first = client.post(REFRESH, json={"refresh_token": old_refresh})
    assert first.status_code == 200
    new_refresh = first.json()["data"]["refresh_token"]
    assert new_refresh != old_refresh

    # 旧令牌必须已失效
    again = client.post(REFRESH, json={"refresh_token": old_refresh})
    assert again.status_code == 401
    assert again.json()["code"] == int(ErrorCode.REFRESH_TOKEN_INVALID)

    # 新令牌可用
    assert client.post(REFRESH, json={"refresh_token": new_refresh}).status_code == 200


def test_refresh_with_garbage_token_is_40102(client: TestClient) -> None:
    resp = client.post(REFRESH, json={"refresh_token": "rt_not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == int(ErrorCode.REFRESH_TOKEN_INVALID)


def test_logout_revokes_refresh_token(client: TestClient, registered_user: dict[str, str]) -> None:
    token = registered_user["access_token"]
    refresh_token = registered_user["refresh_token"]

    assert client.post(LOGOUT, json={"refresh_token": refresh_token}).status_code == 401, (
        "缺少 Authorization 头时必须 401"
    )

    ok = client.post(
        LOGOUT,
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200

    after = client.post(REFRESH, json={"refresh_token": refresh_token})
    assert after.status_code == 401, "登出后刷新令牌必须失效"


# ============================================================
# A-05 / A-06 当前用户
# ============================================================


def test_me_requires_token(client: TestClient) -> None:
    resp = client.get(ME)
    assert resp.status_code == 401
    assert resp.json()["code"] == int(ErrorCode.ACCESS_TOKEN_INVALID)


def test_me_rejects_malformed_authorization_header(client: TestClient) -> None:
    for header in ("", "Token abc", "Bearer", "Bearer "):
        resp = client.get(ME, headers={"Authorization": header})
        assert resp.status_code == 401, f"头为 {header!r} 时应 401"


def test_me_masks_phone_and_email(client: TestClient) -> None:
    """**脱敏返回**：完整值不通过任何接口返回（05-接口设计 §5.2）。

    完整手机号一旦出现在响应里，就可能被日志、截图、浏览器缓存带出。
    """
    _register(client, phone="13812345678", email="zhangsan@example.com")
    login = client.post(LOGIN, json={"account": "13812345678", "password": "abc12345"}).json()["data"]

    data = client.get(ME, headers={"Authorization": f"Bearer {login['access_token']}"}).json()["data"]

    assert data["phone"] == "138****5678"
    assert "13812345678" not in str(data), "响应中不得出现完整手机号"
    assert data["email"] is not None and data["email"] != "zhangsan@example.com"
    assert "zhangsan" not in str(data["email"]), "响应中不得出现完整邮箱本地部分"
    assert isinstance(data["id"], str)


def test_update_profile(client: TestClient, registered_user: dict[str, str]) -> None:
    headers = {"Authorization": f"Bearer {registered_user['access_token']}"}
    resp = client.put(
        ME,
        json={"real_name": "张三", "org_name": "某某科技有限公司"},
        headers=headers,
    )
    assert resp.status_code == 200
    profile = resp.json()["data"]["profile"]
    assert profile["real_name"] == "张三"
    assert profile["org_name"] == "某某科技有限公司"


def test_update_profile_ignores_unspecified_fields(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    """只传部分字段时，其余字段不应被清空。"""
    headers = {"Authorization": f"Bearer {registered_user['access_token']}"}
    client.put(ME, json={"real_name": "李四", "org_name": "原公司"}, headers=headers)
    resp = client.put(ME, json={"org_role": "法务"}, headers=headers)

    profile = resp.json()["data"]["profile"]
    assert profile["real_name"] == "李四", "未指定的字段不应被清空"
    assert profile["org_name"] == "原公司"
    assert profile["org_role"] == "法务"
