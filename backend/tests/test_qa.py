"""问答切片测试（M3 的 E 组）—— E-01 ~ E-05。

⚠️ 用 `e2e_client`：回答由**后台流水线**生成，必须在"允许真实提交"的环境里跑。

⚠️ **回答溯源**是本组的核心断言对象：有依据时必须给出可读引用；
无依据时必须 `has_citation = false`（"溯源不了的时候要说出来"）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ErrorCode
from app.infra import llm as llm_module

SESSIONS = "/api/v1/qa/sessions"
KB = "/api/v1/kb/documents"

CORPUS = """中华人民共和国民法典（节选）

第五百八十五条 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金。约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。"""


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """切到 `fake` 提供方。

    ⚠️ 测试基线（conftest）把提供方钉在 `stub`，即"AI 未接入"——
    因此凡是要走到**生成成功**的用例，都必须显式切到 `fake`。
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_provider", "fake")


def _auth(client: TestClient, phone: str = "13800000041") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": "abc12345", "verify_code": "000000"},
    )
    resp = client.post("/api/v1/auth/login", json={"account": phone, "password": "abc12345"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _create_session(client: TestClient, headers: dict[str, str], **kwargs) -> str:
    resp = client.post(SESSIONS, json=kwargs, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["session_id"]


def _ask(client: TestClient, headers: dict[str, str], session_id: str, content: str, key: str = "ask-1"):
    return client.post(
        f"{SESSIONS}/{session_id}/messages",
        json={"content": content},
        headers={**headers, "Idempotency-Key": key},
    )


def _seed_knowledge(client: TestClient, headers: dict[str, str]) -> None:
    document_id = client.post(
        KB,
        json={
            "doc_type": "law",
            "title": "民法典（节选）",
            "law_name": "中华人民共和国民法典",
            "effective_date": "2021-01-01",
            "content": CORPUS,
        },
        headers=headers,
    ).json()["data"]["document_id"]
    client.post(f"{KB}/{document_id}/index", json={"force": False}, headers=headers)


# ============================================================
# E-01 创建会话
# ============================================================


def test_create_session(client: TestClient) -> None:
    headers = _auth(client)

    resp = client.post(SESSIONS, json={"title": "关于违约金的问题"}, headers=headers)

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert isinstance(data["session_id"], str)
    assert data["status"] == "active"
    assert data["message_count"] == 0


def test_create_session_without_title(client: TestClient) -> None:
    headers = _auth(client)
    session_id = _create_session(client, headers)

    assert client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]["title"] is None


def test_qa_requires_auth(client: TestClient) -> None:
    assert client.get(SESSIONS).status_code == 401
    assert client.post(SESSIONS, json={}).status_code == 401


# ============================================================
# E-02 会话列表
# ============================================================


def test_list_sessions_filters_and_paginates(client: TestClient) -> None:
    headers = _auth(client)
    for index in range(3):
        _create_session(client, headers, title=f"会话 {index}")

    page = client.get(f"{SESSIONS}?page=1&page_size=2", headers=headers).json()["data"]
    assert page["total"] == 3
    assert len(page["items"]) == 2

    active = client.get(f"{SESSIONS}?status=active", headers=headers).json()["data"]
    assert active["total"] == 3

    archived = client.get(f"{SESSIONS}?status=archived", headers=headers).json()["data"]
    assert archived["total"] == 0

    assert client.get(f"{SESSIONS}?page_size=9999", headers=headers).status_code == 400
    assert client.get(f"{SESSIONS}?sort=drop-table", headers=headers).status_code == 400


def test_list_sessions_only_returns_own(client: TestClient) -> None:
    mine = _auth(client, phone="13800000041")
    theirs = _auth(client, phone="13800000042")
    _create_session(client, mine, title="我的会话")

    listing = client.get(SESSIONS, headers=theirs).json()["data"]

    assert listing["total"] == 0


# ============================================================
# E-03 会话详情
# ============================================================


def test_missing_session_is_40402(client: TestClient) -> None:
    headers = _auth(client)

    resp = client.get(f"{SESSIONS}/99999999", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.QA_SESSION_NOT_FOUND)


def test_other_user_session_is_40301(client: TestClient) -> None:
    mine = _auth(client, phone="13800000041")
    theirs = _auth(client, phone="13800000042")
    session_id = _create_session(client, mine)

    resp = client.get(f"{SESSIONS}/{session_id}", headers=theirs)

    assert resp.status_code == 403
    assert resp.json()["code"] == int(ErrorCode.FORBIDDEN)


# ============================================================
# E-04 提问（异步）
# ============================================================


def test_ask_returns_preallocated_ids_and_is_idempotent(client: TestClient, monkeypatch) -> None:
    """`assistant_message_id` **预分配**，前端据此先占位再原地替换。"""
    from app.slices.qa import service

    monkeypatch.setattr(service, "enqueue", lambda **kwargs: None)
    headers = _auth(client)
    session_id = _create_session(client, headers)

    first = _ask(client, headers, session_id, "违约金过高能调整吗？", key="same")
    assert first.status_code == 202
    body = first.json()["data"]
    assert body["status"] == "pending"
    assert body["user_message_id"] != body["assistant_message_id"]

    second = _ask(client, headers, session_id, "违约金过高能调整吗？", key="same")
    assert second.json()["data"] == body, "同一幂等键必须返回首次结果"


def test_ask_requires_idempotency_key(client: TestClient) -> None:
    headers = _auth(client)
    session_id = _create_session(client, headers)

    resp = client.post(f"{SESSIONS}/{session_id}/messages", json={"content": "x"}, headers=headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


def test_ask_generates_answer_with_citations(e2e_client, fake_llm) -> None:
    """**完整链路**：知识库有依据 → 回答带可读引用，`has_citation = true`。"""
    headers = _auth(e2e_client)
    _seed_knowledge(e2e_client, headers)
    session_id = _create_session(e2e_client, headers, title="违约金问题")

    asked = _ask(e2e_client, headers, session_id, "合同里约定的违约金过高，能调整吗？")
    assert asked.status_code == 202

    detail = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]
    assert detail["messages"]["total"] == 2

    user_message, answer = detail["messages"]["items"]
    assert user_message["role"] == "user"
    assert user_message["has_citation"] is False

    assert answer["role"] == "assistant"
    assert answer["content"], "回答内容应由流水线填充"
    assert answer["has_citation"] is True
    assert answer["model_name"]
    assert answer["latency_ms"] is not None

    assert answer["citations"], "有依据时必须给出引用"
    citation = answer["citations"][0]
    assert citation["law_name"] == "中华人民共和国民法典"
    assert citation["article_no"] == "第五百八十五条"
    assert citation["quoted_text"]


def test_answer_without_retrieval_has_no_citation(e2e_client) -> None:
    """**溯源的反面**：知识库为空时不得假装有依据。

    这是需求里的硬要求 —— 溯源不了的时候要说出来（03-概要设计 §5.3）。
    """
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)

    _ask(e2e_client, headers, session_id, "一个知识库里完全没有的问题")

    answer = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]["messages"]["items"][
        1
    ]
    assert answer["role"] == "assistant"
    assert answer["has_citation"] is False
    assert answer["citations"] == []


def test_answer_failure_is_written_into_content(e2e_client) -> None:
    """生成失败：`qa_message` 没有状态列，失败只能写进 `content`。"""
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)
    # 默认 stub 提供方 → 生成必然失败

    _ask(e2e_client, headers, session_id, "任意问题")

    answer = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]["messages"]["items"][
        1
    ]
    assert answer["content"], "失败必须留下可读内容，不能是空字符串"
    assert answer["has_citation"] is False


def test_ask_after_archive_is_40909(e2e_client) -> None:
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)
    assert e2e_client.delete(f"{SESSIONS}/{session_id}", headers=headers).status_code == 200

    resp = _ask(e2e_client, headers, session_id, "还能问吗")

    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.SESSION_ARCHIVED)


# ============================================================
# E-05 归档
# ============================================================


def test_archive_keeps_messages(e2e_client) -> None:
    """**归档而非物理删除**：历史问答保留可查。"""
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)
    _ask(e2e_client, headers, session_id, "第一个问题")

    resp = e2e_client.delete(f"{SESSIONS}/{session_id}", headers=headers)

    assert resp.status_code == 200
    detail = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]
    assert detail["status"] == "archived"
    assert detail["messages"]["total"] == 2, "归档后消息必须仍在"


def test_default_title_comes_from_first_question(e2e_client) -> None:
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)

    _ask(e2e_client, headers, session_id, "这是一个很长的问题用来验证缺省标题的生成规则")

    detail = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]
    assert detail["title"]


def test_messages_are_paginated(e2e_client, monkeypatch) -> None:
    from app.slices.qa import service

    monkeypatch.setattr(service, "enqueue", lambda **kwargs: None)
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)
    for index in range(3):
        _ask(e2e_client, headers, session_id, f"问题 {index}", key=f"p-{index}")

    first_page = e2e_client.get(f"{SESSIONS}/{session_id}?page=1&page_size=2", headers=headers).json()["data"]
    assert first_page["messages"]["total"] == 6
    assert len(first_page["messages"]["items"]) == 2
    assert first_page["messages"]["items"][0]["role"] == "user"


def test_answer_uses_fake_provider_when_configured(e2e_client, fake_llm) -> None:
    """把提供方切成 `fake` 也应能跑通（`.env` 的默认设置即此）。"""
    headers = _auth(e2e_client)
    _seed_knowledge(e2e_client, headers)
    session_id = _create_session(e2e_client, headers)

    _ask(e2e_client, headers, session_id, "违约金过高能调整吗")

    answer = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]["messages"]["items"][
        1
    ]
    assert answer["content"]
    assert answer["has_citation"] is True


def test_llm_module_is_actually_used(e2e_client, monkeypatch) -> None:
    """确认流水线**确实经过** `infra/llm.py` 封装（而不是绕过它）。"""
    calls: list[dict] = []

    def spy(system: str, user: str, schema: dict) -> dict:
        calls.append({"system": system, "schema": schema})
        return {"answer": "由测试替身生成的回答", "used_indexes": []}

    monkeypatch.setattr(llm_module, "complete_structured", spy)
    headers = _auth(e2e_client)
    session_id = _create_session(e2e_client, headers)

    _ask(e2e_client, headers, session_id, "任意问题")

    assert calls, "流水线必须调用 infra/llm.py 的封装"
    answer = e2e_client.get(f"{SESSIONS}/{session_id}", headers=headers).json()["data"]["messages"]["items"][
        1
    ]
    assert answer["content"] == "由测试替身生成的回答"
