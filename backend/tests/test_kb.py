"""知识库切片测试（M3 的 D 组）—— D-01 ~ D-05。

含两组：
- **切分规则**的单元测试（`chunking.py`）—— 这是最容易做错、后果最严重的一环
  （按字符硬切会让检索到半句法条）；
- **接口行为**的端到端测试 —— 索引是异步的，用 `e2e_client`。

⚠️ 检索排序**不做断言**：stub 嵌入是哈希伪向量，排序没有语义。
这里只断言"该被检索到的块确实在结果里"以及过滤规则是否生效。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import ErrorCode
from app.slices.kb.chunking import split_into_chunks

KB = "/api/v1/kb/documents"

CORPUS = """中华人民共和国民法典（节选）

第五百八十四条 当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失。

第五百八十五条 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金。约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。"""

ABOLISHED_CORPUS = """中华人民共和国经济合同法（已废止）

第二十九条 由于当事人一方的过错，造成经济合同不能履行或者不能完全履行，由有过错的一方承担违约责任。"""


def _auth(client: TestClient, phone: str = "13800000031") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": "abc12345", "verify_code": "000000"},
    )
    resp = client.post("/api/v1/auth/login", json={"account": phone, "password": "abc12345"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _create(client: TestClient, headers: dict[str, str], content: str = CORPUS, **overrides):
    payload = {
        "doc_type": "law",
        "corpus_tier": 1,
        "title": "中华人民共和国民法典（节选）",
        "law_name": "中华人民共和国民法典",
        "effective_date": "2021-01-01",
        "content": content,
    }
    payload.update(overrides)
    return client.post(KB, json=payload, headers=headers)


def _index(client: TestClient, headers: dict[str, str], document_id: str):
    return client.post(f"{KB}/{document_id}/index", json={"force": False}, headers=headers)


# ============================================================
# 切分规则（单元）
# ============================================================


def test_chunking_splits_by_article_and_keeps_offsets() -> None:
    """按"条"切分，且 `char_start/char_end` 能精确定位回原文（支撑回答溯源）。"""
    chunks = split_into_chunks(CORPUS)

    assert len(chunks) == 2
    assert [c.article_no for c in chunks] == ["第五百八十四条", "第五百八十五条"]
    assert all(c.chunk_type == "article" for c in chunks)

    for chunk in chunks:
        # 偏移必须与内容自洽 —— 前端高亮与引用定位都依赖这一点
        assert CORPUS[chunk.char_start : chunk.char_end].strip() == chunk.content
        assert chunk.content.startswith(chunk.article_no)


def test_chunking_falls_back_to_paragraphs_without_articles() -> None:
    """没有条号时退化为按段落，**仍然不是按字符硬切**。"""
    text = "第一段内容。\n继续第一段。\n\n第二段内容。"

    chunks = split_into_chunks(text)

    assert [c.chunk_type for c in chunks] == ["paragraph", "paragraph"]
    assert chunks[0].content == "第一段内容。\n继续第一段。"
    assert chunks[1].content == "第二段内容。"


def test_chunking_handles_empty_text() -> None:
    assert split_into_chunks("") == []
    assert split_into_chunks("   \n  ") == []


# ============================================================
# D-01 创建语料
# ============================================================


def test_create_document_returns_hash_and_chunk_count(client: TestClient) -> None:
    headers = _auth(client)

    resp = _create(client, headers)

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert isinstance(data["document_id"], str)
    assert len(data["content_hash"]) == 64
    assert data["char_count"] == len(CORPUS)
    assert data["chunk_count"] == 2, "创建时即完成切分（kb_document 不存全文，分块是全文的唯一载体）"
    assert data["index_status"] == "pending", "尚未向量化"


def test_duplicate_content_is_40908(client: TestClient) -> None:
    headers = _auth(client)
    assert _create(client, headers).status_code == 201

    resp = _create(client, headers, title="换个标题但内容相同")

    assert resp.status_code == 409
    assert resp.json()["code"] == int(ErrorCode.KB_DOC_EXISTS)


def test_kb_requires_auth(client: TestClient) -> None:
    assert client.get(KB).status_code == 401
    assert client.post(KB, json={"doc_type": "law", "title": "x", "content": "y"}).status_code == 401


# ============================================================
# D-02 索引（异步）
# ============================================================


def test_index_marks_document_indexed(
    e2e_client,
) -> None:
    headers = _auth(e2e_client)
    document_id = _create(e2e_client, headers).json()["data"]["document_id"]

    triggered = _index(e2e_client, headers, document_id)
    assert triggered.status_code == 202
    assert triggered.json()["data"]["task_id"] == document_id, "无索引任务表，任务标识即文档标识"

    detail = e2e_client.get(f"{KB}/{document_id}", headers=headers).json()["data"]
    assert detail["index_status"] == "indexed"
    assert detail["indexed_at"] is not None
    assert detail["chunk_count"] == 2


# ============================================================
# D-03 / D-04 列表与详情
# ============================================================


def test_list_documents_filters_and_paginates(client: TestClient) -> None:
    headers = _auth(client)
    _create(client, headers)
    _create(client, headers, content=ABOLISHED_CORPUS, title="经济合同法", doc_type="template", corpus_tier=2)

    page = client.get(f"{KB}?page=1&page_size=1", headers=headers).json()["data"]
    assert page["total"] == 2
    assert len(page["items"]) == 1

    laws = client.get(f"{KB}?doc_type=law", headers=headers).json()["data"]
    assert laws["total"] == 1

    tiers = client.get(f"{KB}?corpus_tier=2", headers=headers).json()["data"]
    assert tiers["total"] == 1

    bad = client.get(f"{KB}?page_size=9999", headers=headers)
    assert bad.status_code == 400
    assert bad.json()["code"] == int(ErrorCode.PAGE_OUT_OF_RANGE)


def test_detail_returns_chunks_and_reconstructed_content(client: TestClient) -> None:
    headers = _auth(client)
    document_id = _create(client, headers).json()["data"]["document_id"]

    detail = client.get(f"{KB}/{document_id}", headers=headers).json()["data"]

    assert detail["content_hash"] and detail["char_count"] == len(CORPUS)
    assert len(detail["chunks"]) == 2
    assert detail["chunks"][0]["article_no"] == "第五百八十四条"
    # 全文由分块拼接重建（分块间隙的空白不可还原）
    assert detail["content"].startswith("第五百八十四条")


def test_missing_document_is_40403(client: TestClient) -> None:
    headers = _auth(client)

    resp = client.get(f"{KB}/99999999", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.KB_DOC_NOT_FOUND)


# ============================================================
# D-05 语义检索
# ============================================================


def test_search_finds_indexed_chunks(e2e_client) -> None:
    headers = _auth(e2e_client)
    document_id = _create(e2e_client, headers).json()["data"]["document_id"]
    _index(e2e_client, headers, document_id)

    resp = e2e_client.get("/api/v1/kb/search?q=违约金过高&top_k=5", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["query"] == "违约金过高"
    assert len(data["items"]) == 2
    # 排序无语义（stub 嵌入），但命中的块必须带齐可读引用所需的信息
    for item in data["items"]:
        assert item["article_no"].startswith("第五百八")
        assert item["content"]
        assert item["char_end"] > item["char_start"]
        assert item["effective_date"] == "2021-01-01"


def test_search_excludes_abolished_by_default(e2e_client) -> None:
    """**默认排除已废止法条** —— 据以作答是本项目最严重的失败形态之一。"""
    headers = _auth(e2e_client)
    document_id = _create(
        e2e_client,
        headers,
        content=ABOLISHED_CORPUS,
        title="经济合同法",
        abolished_date="1999-10-01",
    ).json()["data"]["document_id"]
    _index(e2e_client, headers, document_id)

    default = e2e_client.get("/api/v1/kb/search?q=违约责任", headers=headers).json()["data"]
    assert default["items"] == [], "已废止法条默认不应出现"

    included = e2e_client.get("/api/v1/kb/search?q=违约责任&include_abolished=true", headers=headers).json()[
        "data"
    ]
    assert len(included["items"]) == 1, "显式要求时才返回"


def test_search_validates_params(client: TestClient) -> None:
    headers = _auth(client)

    assert client.get("/api/v1/kb/search?q=&top_k=5", headers=headers).status_code == 400
    assert client.get("/api/v1/kb/search?q=x&top_k=99", headers=headers).status_code == 400
    assert client.get("/api/v1/kb/search?q=x&top_k=0", headers=headers).status_code == 400


def test_search_on_empty_index_returns_no_items(client: TestClient) -> None:
    headers = _auth(client)

    resp = client.get("/api/v1/kb/search?q=任意内容", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []
