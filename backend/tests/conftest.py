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
def _memory_idempotency_store(monkeypatch) -> Generator[dict[str, dict]]:
    """幂等缓存的进程内替身。

    ⚠️ **必须替换**：真实实现写 Redis，且 TTL 24 小时。若不替换，
    **测试之间会互相污染** —— 前一个用例缓存的 `task_id` 属于它自己那个
    已被丢弃的内存库；后一个用例若用了同一个 key，就会拿到一个
    "任务创建成功、随即却查不到"的诡异响应。

    症状具有误导性：单跑通过、连着跑失败，看起来像并发或事务问题。
    """
    store: dict[str, dict] = {}

    from app.core import idempotency

    monkeypatch.setattr(idempotency, "load", lambda key: store.get(key))
    monkeypatch.setattr(idempotency, "save", lambda key, payload: store.update({key: payload}))
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


@pytest.fixture
def sample_pdf() -> bytes:
    """一份结构完整的 PDF 合同，供上传与审查用例使用。"""
    text = "Purchase Contract. Party B shall deliver goods within 30 days."
    content = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def e2e_client(monkeypatch, _temp_storage):
    """**允许真实提交**的端到端环境，用于审查流水线。

    ⚠️ 与 `client` 夹具的区别在于隔离方式：
    - `client` 用「事务 + 用例结束回滚」保证隔离，因此**不能承受 commit**；
    - 审查流水线必须分阶段 commit（否则轮询看不到进度），所以这里改成
      「**每个用例一个全新的内存库 + 真实提交**」，并在结束时丢弃整个库。

    同时把流水线的会话工厂与存储指向同一套测试资源 —— 流水线运行在请求之外，
    用的是它自己创建的会话与存储引用。
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    from app.slices.review import pipeline as review_pipeline

    app = create_app()

    def _override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(review_pipeline, "SessionLocal", factory)
    # 流水线是具名导入，持有自己的 get_storage 引用，需单独替换
    monkeypatch.setattr(review_pipeline, "get_storage", lambda: _temp_storage)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    engine.dispose()
