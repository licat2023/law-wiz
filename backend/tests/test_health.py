"""健康检查（F-01）的契约测试。

**为什么需要这一组**：`/health` 在数据库不可用时返回 503，但起初
**响应体仍是 `code: 0 / message: "ok"`** —— 与 05-接口设计 §3.2 的
「前端应以 `code` 为准判断业务结果」直接矛盾：照约定写的前端会把
「服务不可用」当成「服务正常」。功能上无人会立刻察觉，
因为健康检查平时总是返回 200。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import ErrorCode, http_status_for


def test_health_ok_when_dependencies_up(client: TestClient) -> None:
    """依赖正常时返回 200 + code 0 + status ok。

    测试夹具用内存 SQLite，因此 database 恒为 ok；
    Redis 未起时 redis 为 unavailable，整体降级为 degraded —— 两者都可接受。
    """
    resp = client.get("/api/v1/health")
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["status"] in ("ok", "degraded")
    assert body["data"]["components"]["database"] == "ok"


def test_health_returns_503_and_failure_code_when_database_down(client: TestClient) -> None:
    """**数据库不可用时必须是失败响应体。**

    断言三件事，缺一不可：
    1. HTTP 503；
    2. `code` 非 0（否则"以 code 为准"的前端会误判为成功）；
    3. 诊断信息仍在 `data` 里（`components.database == unavailable`），
       使排障时能看到是哪个组件挂了。
    """
    from app.api import get_db
    from app.main import create_app

    app = create_app()

    class _BrokenSession:
        def execute(self, *_a, **_kw):
            raise RuntimeError("模拟数据库不可用")

    app.dependency_overrides[get_db] = lambda: _BrokenSession()

    with TestClient(app) as c:
        resp = c.get("/api/v1/health")

    body = resp.json()

    assert resp.status_code == 503, f"数据库不可用必须返回 503，实际 {resp.status_code}"
    assert body["code"] != 0, (
        f"HTTP 503 时 `code` 必须非 0（实际 {body['code']}）。"
        "否则按「以 code 为准」约定写的前端会把服务不可用当成成功。"
    )
    assert body["code"] == int(ErrorCode.DATABASE_UNAVAILABLE)
    assert body["data"]["status"] == "unavailable"
    assert body["data"]["components"]["database"] == "unavailable"


def test_database_unavailable_maps_to_503() -> None:
    """错误码 → HTTP 状态码的映射必须覆盖数据库不可用。"""
    assert http_status_for(ErrorCode.DATABASE_UNAVAILABLE) == 503


def test_docs_endpoints_disabled_in_production(monkeypatch) -> None:
    """生产环境必须关闭 `/docs` 与 `/openapi.json`。

    二者会完整暴露接口契约（字段、错误码、参数约束），等于给攻击者
    一份免费的信息收集清单。开发/测试环境保留，因此关闭**只由 app_env 驱动**。
    """
    from app.core.config import get_settings
    from app.main import create_app

    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    # 让启动校验通过：生产要求独立密钥、关闭固定验证码、禁用 fake。
    monkeypatch.setattr(settings, "allow_fixed_verify_code", False)
    monkeypatch.setattr(settings, "jwt_secret", "production-grade-secret")
    monkeypatch.setattr(settings, "llm_provider", "stub")
    monkeypatch.setattr(settings, "debug", False)

    with TestClient(create_app()) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404


def test_health_response_declares_503_in_openapi(client: TestClient) -> None:
    """503 必须出现在 OpenAPI 里。

    FastAPI 默认只把 200 写进 OpenAPI，未声明时 Swagger 上会显示
    `Undocumented`，前端与测试同学无法从文档得知 503 是可能的结果。
    """
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/v1/health"]["get"]["responses"]

    assert "200" in responses
    assert "503" in responses, f"OpenAPI 未声明 503 响应，实际只有 {list(responses)}"


def test_health_does_not_leak_secrets(client: TestClient) -> None:
    """健康检查**不得**返回凭据、连接串或内部地址。"""
    raw = client.get("/api/v1/health").text

    for forbidden in ("password", "secret", "mysql+pymysql", "redis://", "127.0.0.1", "jwt"):
        assert forbidden not in raw.lower(), f"健康检查响应中出现了敏感内容：{forbidden}"
