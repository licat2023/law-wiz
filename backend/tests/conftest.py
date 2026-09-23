"""测试夹具。

**为什么用 SQLite 而不是 MySQL**：单元测试要能在任何机器上零依赖运行
（包括没起 MySQL 的队友机器与 CI）。代价是 **SQLite 不校验外键**，
因此"外键约束是否生效"这类检查**必须连真实 MySQL 验证**，不能靠这里的用例。

⚠️ 存储引擎与应用同为**异步**（`aiosqlite`）。夹具与请求处理器运行在
**不同的事件循环**里，因此引擎一律用 `NullPool`：每条连接在"创建它的那个
循环"内用完即关，不跨循环复用。SQLite 内存库 + `StaticPool` 恰恰做不到这一点
（连接会被跨循环复用），所以改为**每个用例一个临时文件库** ——
顺带获得更强的隔离：用例之间天然零污染，也不需要清库脚本。

⚠️ 另一个刻意的取舍：**不引入 `fakeredis`**。刷新令牌改用下面的内存替身，
避免为一个测试再拉一个依赖。

⚠️ 存储也被替换到临时目录 —— 测试**不得**往项目里的 `.data/` 写真实文件。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api import get_db
from app.infra.db.base import Base
from app.main import create_app


def build_engine(url: str) -> AsyncEngine:
    """构造测试引擎。集中一处，保证 `client` 与 `e2e_client` 用同一套参数。"""
    return create_async_engine(url, poolclass=NullPool)


async def create_schema(engine: AsyncEngine) -> None:
    import app.models  # noqa: F401  确保全部模型已注册到 metadata

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture
def engine(tmp_path) -> Generator[AsyncEngine]:
    """整个用例独享一个 SQLite 文件库（见文件头说明）。"""
    eng = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    asyncio.run(create_schema(eng))
    yield eng
    asyncio.run(eng.dispose())


@pytest.fixture
def db_session_factory(engine: AsyncEngine):
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _memory_refresh_store(monkeypatch) -> Generator[dict[str, int]]:
    """刷新令牌存储的内存替身，使认证用例不依赖 Redis。"""
    store: dict[str, int] = {}

    from app.infra import cache

    async def store_token(user_id: int, token: str) -> None:
        from app.core.security import refresh_token_digest

        store[refresh_token_digest(token)] = user_id

    async def consume_token(token: str) -> int:
        from app.core.errors import BusinessError, ErrorCode
        from app.core.security import refresh_token_digest

        digest = refresh_token_digest(token)
        if digest not in store:
            raise BusinessError(ErrorCode.REFRESH_TOKEN_INVALID, "刷新令牌无效或已被撤销")
        return store.pop(digest)

    async def revoke(token: str, *, user_id: int | None = None) -> None:
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


class _InMemoryRedis:
    """Redis 客户端的替身：只支撑 `ping`（其余读写路径都有各自的内存替身）。

    ⚠️ **连 `ping` 也必须替掉**：真实客户端会把连接绑定在**创建它的那个事件循环**上，
    而每个 `TestClient` 跑在自己的循环里 —— 用例结束后连接被清理时会碰到已关闭的
    循环（`RuntimeError: Event loop is closed`）。该缺陷**只在开发机恰好起了 Redis
    时复现**，属"同一份代码在不同机器上结论不同"，必须消除。
    """

    async def ping(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch) -> None:
    """禁止测试进程创建真实 Redis 客户端（见 `_InMemoryRedis` 的说明）。"""
    from app.infra import cache

    monkeypatch.setattr(cache, "get_redis", _InMemoryRedis)


@pytest.fixture(autouse=True)
def _baseline_settings(monkeypatch) -> None:
    """把与外部能力相关的配置钉在**测试基线**上。

    ⚠️ **必须这么做**：`get_settings()` 会读取**开发者本机的 `.env`**。
    若本机为了演示把 `llm_provider` 设成 `fake`（返回写死的假结论），
    测试结果就会随机器而变 —— **"同一份代码在不同机器上结论不同"是测试
    不能接受的属性**，也违背 AGENTS.md 的"验证必须针对全新 clone"。

    需要非基线取值的用例自行用 monkeypatch 覆盖（见 `test_infra_ai.py`）。
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "stub")
    monkeypatch.setattr(settings, "ocr_provider", "stub")
    monkeypatch.setattr(settings, "vector_backend", "memory")


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

    async def _load(scope: str, key: str) -> dict | None:
        return store.get(f"{scope}:{key}")

    async def _save(scope: str, key: str, payload: dict) -> None:
        store[f"{scope}:{key}"] = payload

    monkeypatch.setattr(idempotency, "load", _load)
    monkeypatch.setattr(idempotency, "save", _save)
    yield store


@pytest.fixture(autouse=True)
def _memory_rate_limit_store(monkeypatch) -> Generator[dict[str, int]]:
    """限流计数的内存替身。

    ⚠️ **必须替换**：真实实现写 Redis。不替换会**跨用例累积计数** ——
    某个用例多打几次接口，就会让后续用例莫名收到 `42901`
    （与幂等缓存污染属于同一类问题：测试依赖了外部共享状态）。

    ⚠️ 只替换 `_incr`（存储），**窗口划分与阈值判断仍走真实实现** ——
    替身不复制业务逻辑，避免它与生产逻辑分叉。
    """
    counters: dict[str, int] = {}

    async def _incr(key: str, ttl: int) -> int:
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    from app.infra import ratelimit

    monkeypatch.setattr(ratelimit, "_incr", _incr)
    yield counters


@pytest.fixture(autouse=True)
def _temp_storage(tmp_path, monkeypatch):
    """把文件存储指向临时目录，避免测试污染项目的 `.data/`。"""
    from app.infra import storage as storage_module
    from app.slices.files import service as files_service

    instance = storage_module.LocalStorage(str(tmp_path / "storage-root"))
    monkeypatch.setattr(storage_module, "_storage", instance)
    monkeypatch.setattr(files_service, "get_storage", lambda: instance)
    return instance


def _override_db(db_session_factory):
    """把 `get_db` 依赖替换为测试引擎的会话工厂。

    ⚠️ 不能像同步时代那样直接返回一个共享会话对象：异步会话的底层连接
    绑定在创建它的事件循环上，而请求由 `TestClient` 在另一个循环里执行。
    改为"每次请求按需开会话"后，连接始终在请求自己的循环内创建与关闭。
    """

    async def _get_db() -> AsyncGenerator:
        async with db_session_factory() as session:
            yield session

    return _get_db


@pytest.fixture
def client(db_session_factory) -> Generator[TestClient]:
    """测试客户端。数据库依赖被替换为测试会话。"""
    app = create_app()
    app.dependency_overrides[get_db] = _override_db(db_session_factory)
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
def make_pdf():
    """按页数构造合法 PDF（每页一段文本），用于验证页数上限等路径。

    结构与 `sample_pdf` 相同，只是把页对象与内容流按页数展开。
    """

    def _build(page_texts: list[str]) -> bytes:
        n = len(page_texts)
        font_num = 3 + 2 * n
        kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        ]
        for i, text in enumerate(page_texts):
            content = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Contents {4 + 2 * i} 0 R /Resources << /Font << /F1 {font_num} 0 R >> >> >>".encode()
            )
            objects.append(
                b"<< /Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream"
            )
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

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

    return _build


@pytest.fixture
def e2e_client(monkeypatch, _temp_storage, db_session_factory) -> Generator[TestClient]:
    """**允许真实提交**的端到端环境，用于审查、索引与问答流水线。

    ⚠️ 与 `client` 夹具的区别在于**流水线运行在请求之外**：它自建会话
    （`SessionLocal`）并分阶段提交。因此这里必须把三条流水线的会话工厂
    一并指向测试引擎 —— 漏掉任何一条，该流水线就会去连真实的 MySQL。

    数据库隔离由 `engine` 夹具保证（每个用例一个全新的文件库）。
    """
    from app.slices.kb import pipeline as kb_pipeline
    from app.slices.qa import pipeline as qa_pipeline
    from app.slices.review import pipeline as review_pipeline

    app = create_app()
    app.dependency_overrides[get_db] = _override_db(db_session_factory)

    monkeypatch.setattr(review_pipeline, "SessionLocal", db_session_factory)
    monkeypatch.setattr(kb_pipeline, "SessionLocal", db_session_factory)
    monkeypatch.setattr(qa_pipeline, "SessionLocal", db_session_factory)
    # 流水线是具名导入，持有自己的 get_storage 引用，需单独替换
    monkeypatch.setattr(review_pipeline, "get_storage", lambda: _temp_storage)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_vector_store():
    """清空进程内的向量索引。

    ⚠️ 它是**模块级全局状态**：不清理的话，一个用例索引进去的内容会被另一个
    用例检索到 —— 与"幂等缓存污染测试"属于同一类问题（测试依赖了共享状态）。
    """
    from app.infra import vector

    vector.clear()
    yield
    vector.clear()
