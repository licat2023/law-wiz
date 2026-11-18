"""Verify service authentication and the two structured inference endpoints."""

import json
import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from ai_service.citations import Citation
from ai_service.config import Settings
from ai_service.errors import InferenceError
from ai_service.main import create_app


class TranscriptModel:
    """Return a selected citation and echo details available to the workflow."""

    async def ainvoke(self, messages):
        transcript = "\n".join(message.content for message in messages)
        details = ["报告原有证据", "上一轮问题", "当轮第二条法条", "核对交付款项"]
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

    def test_ordinary_qa_without_model_does_not_present_search_hits_as_evidence(self):
        async def search(_query, **_context):
            return [
                Citation(document_id="sample", knowledge_base_chunk_id="sample", quoted_text="开发联调样本")
            ]

        app = create_app(Settings(allow_fake_model=True, service_token="fixture-key"), search_laws=search)
        with TestClient(app) as client:
            response = client.post("/internal/qa", headers=self.headers, json={"question": "如何签收？"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("法律问答暂不可用", response.json()["answer"])
        self.assertEqual(response.json()["citations"], [])

    def test_ordinary_qa_persists_only_the_source_the_model_used(self):
        async def search(_query, **_context):
            return [
                Citation(document_id="sample", knowledge_base_chunk_id="sample", quoted_text="开发联调样本"),
                Citation(document_id="law", knowledge_base_chunk_id="law", quoted_text="当轮第二条法条"),
            ]

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=TranscriptModel())
        with TestClient(app) as client:
            response = client.post("/internal/qa", headers=self.headers, json={"question": "如何签收？"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "当轮第二条法条 [1]")
        self.assertEqual([citation["document_id"] for citation in response.json()["citations"]], ["law"])

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
                        "findings": [{"risk_level": "high", "description": "核对交付款项"}],
                    },
                    "history": [{"role": "user", "content": "上一轮问题"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertIn("报告原有证据 上一轮问题 当轮第二条法条 核对交付款项 [1]", answer["answer"])
        self.assertEqual([citation["document_id"] for citation in answer["citations"]], ["two"])

    def test_qa_excludes_templates_and_can_answer_without_legal_sources(self):
        class ChecklistModel:
            async def ainvoke(self, messages):
                if any("开发联调样本文本" in message.content for message in messages):
                    return AIMessage(content='{"answer":"开发联调样本 [1]","citations":[1]}')
                return AIMessage(content='{"answer":"请核对验收条款和签收记录。","citations":[]}')

        async def search(_query, **_context):
            return [
                Citation(
                    document_id="template",
                    knowledge_base_chunk_id="sample",
                    document_type="template",
                    quoted_text="开发联调样本文本",
                ),
            ]

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=ChecklistModel())
        with TestClient(app) as client:
            for report in (None, {"contract_title": "合同", "summary": "摘要"}):
                with self.subTest(report=report):
                    response = client.post(
                        "/internal/qa",
                        headers=self.headers,
                        json={"question": "如何签收？", "report": report},
                    )
                    self.assertEqual(response.status_code, 200)
                    answer = response.json()
                    self.assertIn("未找到直接法律依据", answer["answer"])
                    self.assertIn("请核对验收条款和签收记录。", answer["answer"])
                    self.assertEqual(answer["citations"], [])

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

    def test_qa_stream_delivers_only_answer_text_then_validated_citations(self):
        class ChunkedModel:
            async def astream(self, _messages):
                yield AIMessageChunk(content="", additional_kwargs={"reasoning_content": "内部推理"})
                for content in (
                    '```json\n{"answer":"核对',
                    r"合同\n签收 [",
                    "2]",
                    '记录","citations":[2]}\n```',
                ):
                    yield AIMessageChunk(content=content, response_metadata={"model_name": "fixture-stream"})

        async def search(_query, **_context):
            return [
                Citation(document_id="one", knowledge_base_chunk_id="one", quoted_text="候选法条"),
                Citation(document_id="two", knowledge_base_chunk_id="two", quoted_text="使用的法条"),
            ]

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=ChunkedModel())
        with TestClient(app) as client:
            path = "/internal/qa/stream"
            self.assertEqual(client.post(path, json={"question": "如何签收？"}).status_code, 401)
            for report in (None, {"contract_title": "合同", "summary": "测试摘要"}):
                with self.subTest(report=report):
                    response = client.post(
                        path, headers=self.headers, json={"question": "如何签收？", "report": report}
                    )
                    self.assertEqual(response.status_code, 200)
                    events = [json.loads(line) for line in response.iter_lines()]
                    deltas, final = events[:-1], events[-1]
                    self.assertGreater(len(deltas), 1)
                    self.assertTrue(all(event["type"] == "delta" for event in deltas))
                    preview = "".join(event["text"] for event in deltas)
                    prefix = "报告原有分析\n测试摘要\n\n本轮依据与建议\n" if report else ""
                    self.assertEqual(preview, prefix + "核对合同\n签收 记录")
                    self.assertEqual(final["type"], "result")
                    self.assertEqual(final["result"]["answer"], prefix + "核对合同\n签收 [1]记录")
                    self.assertEqual(final["result"]["model_name"], "fixture-stream")
                    self.assertEqual([item["document_id"] for item in final["result"]["citations"]], ["two"])

    def test_qa_stream_never_promotes_a_truncated_model_response(self):
        class TruncatedModel:
            async def astream(self, _messages):
                yield AIMessageChunk(content='{"answer":"未完成')

        async def search(_query, **_context):
            return []

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=TruncatedModel())
        with TestClient(app) as client:
            response = client.post(
                "/internal/qa/stream", headers=self.headers, json={"question": "如何签收？"}
            )
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.iter_lines()]
        self.assertEqual([event["type"] for event in events], ["delta", "error"])
        self.assertEqual(events[-1]["code"], "model_unavailable")
