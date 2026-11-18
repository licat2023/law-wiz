"""Verify service authentication and the two structured inference endpoints."""

import json
import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from ai_service.citations import Citation
from ai_service.config import Settings
from ai_service.errors import InferenceError
from ai_service.main import create_app


class TranscriptModel:
    """Return a selected citation and echo details available to the workflow."""

    async def ainvoke(self, messages):
        transcript = "\n".join(message.content for message in messages)
        details = ["报告原有证据", "上一轮问题", "当轮第二条法条"]
        found = " ".join(part for part in details if part in transcript)
        return AIMessage(content=json.dumps({"answer": found + " [2]", "citations": [2]}))


class InferenceTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        async def search(query, **context):
            self.calls.append((query, context))
            return []

        app = create_app(Settings(allow_fake_model=True, service_token="fixture-key"), search_laws=search)
        self.client = self.enterContext(TestClient(app))
        self.headers = {
            "Authorization": "Bearer fixture-key",
            "X-Request-ID": "fixture-request",
            "X-Trace-ID": "fixture-trace",
        }

    def test_review_returns_matched_rules_and_propagates_request_context(self):
        response = self.client.post(
            "/internal/review",
            headers=self.headers,
            json={"plain_text": "合同条款", "risk_rules": [{"risk_level": "low", "description": "验收"}]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["extracted_terms"], {"text_length": 4})
        self.assertEqual(response.json()["risk_points"][0]["source_type"], "rule")
        self.assertEqual(
            self.calls, [("合同条款", {"request_id": "fixture-request", "trace_id": "fixture-trace"})]
        )

    def test_qa_requires_a_service_token_and_accepts_report_context(self):
        payload = {"question": "如何处理", "report": {"contract_title": "合同", "summary": "测试摘要"}}
        self.assertEqual(self.client.post("/internal/qa", json=payload).status_code, 401)
        self.assertEqual(self.calls, [])
        response = self.client.post("/internal/qa", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("测试摘要", response.json()["answer"])
        self.assertEqual(response.json()["citations"], [])

    def test_followup_only_persists_citations_from_this_turn(self):
        async def search(_query, **_context):
            return [
                Citation(document_id="one", knowledge_base_chunk_id="one", quoted_text="候选法条"),
                Citation(document_id="two", knowledge_base_chunk_id="two", quoted_text="当轮第二条法条"),
            ]

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=TranscriptModel())
        with TestClient(app) as client:
            response = client.post(
                "/internal/qa",
                headers=self.headers,
                json={
                    "question": "对方不同意怎么办",
                    "report": {
                        "contract_title": "合同",
                        "summary": "摘要",
                        "original_reference": "报告原有证据",
                    },
                    "history": [{"role": "user", "content": "上一轮问题"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertIn("报告原有证据 上一轮问题 当轮第二条法条 [1]", answer["answer"])
        self.assertEqual([citation["document_id"] for citation in answer["citations"]], ["two"])

    def test_knowledge_base_outage_distinguishes_ordinary_and_report_qa(self):
        async def search(_query, **_context):
            raise InferenceError(503, "knowledge_unavailable", "知识库服务暂不可用")

        app = create_app(Settings(allow_fake_model=True, service_token="fixture-key"), search_laws=search)
        with TestClient(app) as client:
            response = client.post("/internal/qa", headers=self.headers, json={"question": "问题"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["code"], "knowledge_unavailable")
            response = client.post(
                "/internal/qa",
                headers=self.headers,
                json={"question": "问题", "report": {"contract_title": "合同", "summary": "摘要"}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("知识库暂不可用", response.json()["answer"])
        self.assertEqual(response.json()["citations"], [])
