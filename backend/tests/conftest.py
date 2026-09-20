"""测试夹具。

**为什么用 SQLite 内存库而不是 MySQL**：单元测试要能在任何机器上零依赖运行
（包括没起 MySQL 的队友机器与 CI）。代价是 **SQLite 不校验外键**，
因此"外键约束是否生效"这类检查**必须连真实 MySQL 验证**，不能靠这里的用例。

⚠️ 另一个刻意的取舍：**不引入 `fakeredis`**。刷新令牌改用下面的内存替身，
避免为一个测试再拉一个依赖。

⚠️ 存储也被替换到临时目录 —— 测试**不得**往项目里的 `.data/` 写真实文件。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import get_db
from app.infra.db.base import Base
from app.main import create_app


@pytest.fixture(scope="session")
def engine():
    """整个测试会话共用一个内存库。

    `StaticPool` 是必需的：SQLite 的 `:memory:` **每条连接都是一个独立的库**，
    没有它就会出现"建表在 A 连接、查询在 B 连接"从而报"表不存在"。
    """
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401  确保全部模型已注册到 metadata

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Generator[Session]:
    """每个用例一个事务，结束即回滚 —— 用例之间互不污染。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _memory_refresh_store(monkeypatch) -> Generator[dict[str, int]]:
    """刷新令牌存储的内存替身，使认证用例不依赖 Redis。

    只替换令牌相关函数，**不动 `ping`** —— 健康检查用例需要它反映真实情况。
    """
    store: dict[str, int] = {}

    from app.infra import cache

    def store_token(user_id: int, token: str) -> None:
        from app.core.security import refresh_token_digest

        store[refresh_token_digest(token)] = user_id

    def consume_token(token: str) -> int:
        from app.core.errors import BusinessError, ErrorCode
        from app.core.security import refresh_token_digest

        digest = refresh_token_digest(token)
        if digest not in store:
            raise BusinessError(ErrorCode.REFRESH_TOKEN_INVALID, "刷新令牌无效或已被撤销")
        return store.pop(digest)

    def revoke(token: str, *, user_id: int | None = None) -> None:
        from app.core.security import refresh_token_digest

        store.pop(refresh_token_digest(token), None)

    monkeypatch.setattr(cache, "store_refresh_token", store_token)
    monkeypatch.setattr(cache, "consume_refresh_token", consume_token)
    monkeypatch.setattr(cache, "revoke_refresh_token", revoke)

    # 服务层使用的是 `from ... import` 的具名导入，因此它模块内的引用也要一并替换，
    # 否则服务层仍指向真实 Redis。
    from app.slices.auth import service

    monkeypatch.setattr(service, "store_refresh_token", store_token)
    monkeypatch.setattr(service, "consume_refresh_token", consume_token)
    monkeypatch.setattr(service, "revoke_refresh_token", revoke)

    yield store


@pytest.fixture(autouse=True)
def _temp_storage(tmp_path, monkeypatch):
    """把文件存储指向临时目录，避免测试污染项目的 `.data/`。"""
    from app.infra import storage as storage_module
    from app.slices.files import service as files_service

    instance = storage_module.LocalStorage(str(tmp_path / "storage-root"))
    monkeypatch.setattr(storage_module, "_storage", instance)
    monkeypatch.setattr(files_service, "get_storage", lambda: instance)
    return instance


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    """测试客户端。数据库依赖被替换为测试会话。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(client: TestClient) -> dict[str, str]:
    """一个已注册并登录的用户，返回其令牌。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"phone": "13800000001", "password": "abc12345", "verify_code": "000000"},
    )
    assert resp.status_code == 201, resp.text

    resp = client.post(
        "/api/v1/auth/login",
        json={"account": "13800000001", "password": "abc12345"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]
