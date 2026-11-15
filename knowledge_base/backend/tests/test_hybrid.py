"""用真实 API、SQLite 与 Chroma 验证混合检索和生效版本。"""

import asyncio
from os import name as os_name
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import bcrypt
import chromadb
import httpx
from chromadb.errors import InternalError
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.auth import ServiceGrant
from app.config import Settings
from app.indexing.keyword import delete_keyword_indexes
from app.infrastructure.reranking import RemoteReranker
from app.infrastructure.vector_store import VectorStore
from app.main import create_app
from scripts.rebuild_keyword_index import queue_rebuild


def ephemeral_store(_path):
    store = object.__new__(VectorStore)
    store.client = chromadb.EphemeralClient()
    return store


class HybridSearchTest(TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        root = Path(directory)
        settings = Settings(
            _env_file=None,
            environment="testing",
            database_url=f"sqlite+aiosqlite:///{(root / 'knowledge.sqlite').as_posix()}",
            data_root=root,
            admin_password_hash=bcrypt.hashpw(b"test-admin", bcrypt.gensalt(rounds=4)).decode(),
            jwt_secret="test-signing-key-sufficiently-long",
            embedding_mode="development",
            auto_create_schema=True,
            worker_enabled=False,
        )
        # Chroma 1.5.8 的 Windows Rust SQLite 层无法打开此机的持久化路径。
        if os_name == "nt":
            self.enterContext(patch("app.lifespan.VectorStore", ephemeral_store))
        self.app = create_app(settings)
        self.client = self.enterContext(TestClient(self.app))
        auth = self.client.post("/api/auth/login", json={"username": "admin", "password": "test-admin"})
        self.client.headers["Authorization"] = f"Bearer {auth.json()['data']['access_token']}"
        self.base = self.data(self.client.post("/api/knowledge-bases", json={"name": "法规"}))
        self.path = f"/api/knowledge-bases/{self.base['id']}"

    def data(self, response):
        payload = response.json()
        self.assertEqual(payload["code"], 0, payload)
        return payload["data"]

    def create(self, title, content, **metadata):
        return self.data(
            self.client.post(
                f"{self.path}/documents",
                json={"title": title, "content": content, "metadata": {"doc_type": "law", **metadata}},
            )
        )

    def process(self, count=1):
        for _ in range(count):
            self.assertTrue(self.client.portal.call(self.app.state.processor.run_once))

    def search(self, query, **options):
        return self.client.post(f"{self.path}/search", json={"query": query, **options})

    def test_normalized_article_matches_and_complete_article_deduplicates(self):
        self.data(
            self.client.patch(
                self.path,
                json={"chunk_size": 12, "chunk_overlap": 3},
            )
        )
        current = self.create("民法典", "第九百八十五条\n没有法律根据取得不当利益，应当返还取得的利益。")
        old = self.create(
            "废止条文",
            "第九百八十五条\n旧版条文。",
            abolished_date="2020-01-01",
        )
        self.create("待生效条文", "第九百八十五条\n未来条文。", effective_date="2099-01-01")
        self.process(3)
        data = self.data(self.search("民法典第985条 不当利益", strategy="hybrid", diagnostics=True))
        self.assertEqual(data["diagnostics"]["keyword"]["status"], "ok")
        self.assertEqual(
            [item["document_id"] for item in data["items"]],
            [current["id"]],
        )
        item = data["items"][0]
        self.assertIn("第九百八十五条", data["article_contents"][item["article_chunk_id"]])
        self.assertIn("keyword", item["retrieval_sources"])
        historical = self.data(
            self.search("第985条", strategy="hybrid", diagnostics=True, include_abolished=True)
        )
        self.assertEqual({item["document_id"] for item in historical["items"]}, {current["id"], old["id"]})

    def test_new_terms_publish_only_after_new_revision_is_indexed(self):
        doc = self.create("测试规则", "第一条\n书面催告。")
        self.process()
        self.data(
            self.client.patch(
                f"{self.path}/documents/{doc['id']}",
                json={"revision": 1, "content": "第二条\n实名签收。"},
            )
        )
        previous = self.data(self.search("第一条", strategy="hybrid", diagnostics=True))
        self.assertEqual(previous["items"][0]["revision"], 1)
        self.process()
        current = self.data(self.search("第二条", strategy="hybrid", diagnostics=True))
        self.assertEqual(current["items"][0]["revision"], 2)
        self.data(self.client.delete(f"{self.path}/documents/{doc['id']}"))
        deleted = self.data(self.search("第二条", strategy="hybrid", diagnostics=True))
        self.assertEqual(deleted["items"], [])
        self.process()
        self.assertEqual(self.client.portal.call(self.keyword_count), 0)

    async def keyword_count(self):
        async with self.app.state.sessions() as db:
            return await db.scalar(text("SELECT count(*) FROM kb_keyword_leaf"))

    def test_keeps_keyword_when_vector_service_fails(self):
        doc = self.create("合同规则", "第一条\n书面催告。")
        self.process()
        with patch.object(self.app.state.vector, "query", side_effect=InternalError("offline")):
            data = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertEqual(data["items"][0]["document_id"], doc["id"])
        self.assertEqual(data["items"][0]["retrieval_sources"], ["keyword"])
        self.assertEqual(data["diagnostics"]["vector"]["status"], "unavailable")

    def test_keeps_vector_when_keyword_store_fails_and_reports_both_failures(self):
        doc = self.create("合同规则", "第一条\n书面催告。")
        self.process()

        async def drop_isolated_postings():
            async with self.app.state.sessions() as db:
                await db.execute(text("DROP TABLE kb_keyword_posting"))
                await db.commit()

        self.client.portal.call(drop_isolated_postings)
        data = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertEqual(data["items"][0]["document_id"], doc["id"])
        self.assertEqual(data["items"][0]["retrieval_sources"], ["vector"])
        self.assertEqual(data["diagnostics"]["keyword"]["status"], "unavailable")
        with patch.object(self.app.state.vector, "query", side_effect=InternalError("offline")):
            response = self.search("书面催告", strategy="hybrid")
        self.assertEqual(response.json()["code"], 50201)

    def test_keyword_connection_invalidation_preserves_vector(self):
        doc = self.create("合同规则", "第一条\n书面催告。")
        self.process()

        async def disconnect(db, *_args):
            await (await db.connection()).invalidate()
            await db.scalar(text("SELECT 1"))
            self.fail("失效连接应报告事务错误")

        with patch("app.retrieval.service.keyword_search", side_effect=disconnect):
            data = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertEqual(data["items"][0]["document_id"], doc["id"])
        self.assertEqual(data["diagnostics"]["keyword"]["status"], "unavailable")

    def test_legacy_document_keeps_vector_until_rebuild_is_published(self):
        doc = self.create("合同规则", "第一条\n书面催告。")
        self.process()
        detail = self.data(self.client.get(f"{self.path}/documents/{doc['id']}"))

        async def simulate_previous_schema():
            async with self.app.state.sessions.begin() as db:
                await delete_keyword_indexes(db, [detail["active_index_id"]])

        self.client.portal.call(simulate_previous_schema)
        jobs = self.client.portal.call(queue_rebuild, self.app.state.sessions, self.base["id"], 10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            self.client.portal.call(queue_rebuild, self.app.state.sessions, self.base["id"], 10), []
        )
        legacy = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertEqual(legacy["items"][0]["index_revision_id"], detail["active_index_id"])
        self.assertEqual(legacy["diagnostics"]["keyword"]["status"], "legacy")
        self.process()
        rebuilt = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertNotEqual(rebuilt["items"][0]["index_revision_id"], detail["active_index_id"])
        self.assertEqual(rebuilt["diagnostics"]["keyword"]["status"], "ok")

    def test_preserves_prior_revision_on_index_write_failure(self):
        doc = self.create("合同规则", "第一条\n书面催告。")
        self.process()
        self.data(
            self.client.patch(
                f"{self.path}/documents/{doc['id']}",
                json={"revision": 1, "content": "第二条\n实名签收。"},
            )
        )
        with patch("app.indexing.jobs.write_keyword_index", side_effect=RuntimeError("offline")):
            self.process()
        data = self.data(self.search("书面催告", strategy="hybrid", diagnostics=True))
        self.assertEqual(data["items"][0]["revision"], 1)
        self.assertEqual(data["diagnostics"]["keyword"]["status"], "ok")

    def test_rerank_timeout_returns_the_same_fused_order(self):
        self.create("电子交易", "第一条\n电子合同应当留存。")
        self.create("商事交易", "第二条\n商事合同采用书面形式。")
        self.process(2)
        baseline = self.data(self.search("合同", strategy="hybrid"))

        async def takes_too_long(_request):
            await asyncio.sleep(30)

        client = httpx.AsyncClient(transport=httpx.MockTransport(takes_too_long))
        self.addCleanup(self.client.portal.call, client.aclose)
        self.app.state.reranker = RemoteReranker(client, "https://rerank.invalid/rerank", "", 0.02)
        result = self.data(self.search("合同", strategy="reranked", diagnostics=True))
        self.assertEqual(result["diagnostics"]["rerank"]["status"], "fallback")
        self.assertEqual(
            [item["chunk_id"] for item in result["items"]], [item["chunk_id"] for item in baseline["items"]]
        )

    def test_rerank_returns_cross_encoder_order_for_valid_scores(self):
        first = self.create("电子交易", "第一条\n电子合同应当留存。")
        second = self.create("商事交易", "第二条\n商事合同采用书面形式。")
        self.process(2)

        def score(request):
            import json

            texts = json.loads(request.content)["texts"]
            return httpx.Response(
                200,
                json=[
                    {"index": index, "score": 0.85 if "商事交易" in value else 0.15}
                    for index, value in reversed(list(enumerate(texts)))
                ],
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(score))
        self.addCleanup(self.client.portal.call, client.aclose)
        self.app.state.reranker = RemoteReranker(client, "https://rerank.invalid/rerank", "", 1)
        result = self.data(self.search("合同", strategy="reranked", diagnostics=True))
        self.assertEqual(result["diagnostics"]["rerank"]["status"], "ok")
        self.assertEqual([item["document_id"] for item in result["items"]], [second["id"], first["id"]])
        self.assertEqual(result["items"][0]["ranks"]["rerank"], 1)

    def test_service_credential_has_normal_search_without_admin_diagnostics(self):
        self.create("业务规则", "第一条\n合同须书面签署。")
        self.process()
        token = "test-service-reader-token"
        self.app.state.grants[token] = ServiceGrant(
            application_id=self.base["application_id"], knowledge_base_ids=[self.base["id"]]
        )
        self.client.headers["Authorization"] = f"Bearer {token}"
        ordinary = self.data(self.search("合同"))
        self.assertNotIn("diagnostics", ordinary)
        self.assertEqual(self.search("合同", strategy="hybrid").json()["code"], 40301)
        self.assertEqual(self.search("合同", diagnostics=True).json()["code"], 40301)
