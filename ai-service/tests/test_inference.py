"""Verify service authentication and the two structured inference endpoints."""

import json
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from ai_service.citations import Citation
from ai_service.config import Settings
from ai_service.errors import InferenceError
from ai_service.main import create_app
from ai_service.review.schemas import ContractTerms


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
            json={
                "plain_text": "合同条款",
                "risk_rules": [{"risk_level": "low", "description": "验收", "clause_text": "条款"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["extracted_terms"], {"text_length": 4})
        point = response.json()["risk_points"][0]
        self.assertEqual(point["source_type"], "rule")
        self.assertEqual((point["clause_text"], point["char_start"], point["char_end"]), ("条款", 2, 4))
        self.assertEqual(
            self.calls, [("合同条款", {"request_id": "fixture-request", "trace_id": "fixture-trace"})]
        )

    def test_review_verifies_excerpts_and_uses_only_law_material(self):
        review_prompts = []

        class ReviewModel:
            def with_structured_output(self, schema, *, method):
                async def answer(prompt):
                    if schema is ContractTerms:
                        return schema()
                    review_prompts.append(prompt)
                    risks = [
                        {
                            "description": "检验时限过短",
                            "source_type": "retrieved_law",
                            "clause_text": "买方须在签收后两小时内完成检验。",
                            "char_start": 0,
                            "char_end": 1,
                            "citations": [{"document_id": "law", "knowledge_base_chunk_id": "clause"}],
                        },
                        {
                            "description": "付款期限待补充",
                            "source_type": "llm_inference",
                            "clause_text": "付款期限为____日。",
                            "legal_basis": "模型附加的未核实依据",
                        },
                        {
                            "description": "改写不可当作原文",
                            "source_type": "llm_inference",
                            "clause_text": "付款期限为五日。",
                            "char_start": 0,
                            "char_end": 1,
                        },
                    ]
                    return schema.model_validate(
                        {"risk_points": [{"risk_level": "high", **risk} for risk in risks]}
                    )

                return SimpleNamespace(ainvoke=answer)

        async def search(_query, **_context):
            return [
                Citation(
                    document_id="sample",
                    knowledge_base_chunk_id="template",
                    document_type="template",
                    quoted_text="模板联调测试文字",
                ),
                Citation(
                    document_id="law",
                    knowledge_base_chunk_id="clause",
                    document_type="law",
                    quoted_text="引用链路测试文段",
                ),
            ]

        text = "测试合同🌿\n买方须在签收后\n两小时内完成检验。\n付款期限为____日。"
        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=ReviewModel())
        with TestClient(app) as client:
            response = client.post("/internal/review", headers=self.headers, json={"plain_text": text})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("模板联调测试文字", review_prompts[0])
        first, second, missing = response.json()["risk_points"]
        self.assertEqual(first["legal_basis"], "引用链路测试文段")
        self.assertIsNone(second["legal_basis"])
        for point, original in (
            (first, "买方须在签收后\n两小时内完成检验。"),
            (second, "付款期限为____日。"),
        ):
            self.assertEqual(point["clause_text"], original)
            self.assertEqual(text[point["char_start"] : point["char_end"]], original)
        self.assertEqual(
            (missing["clause_text"], missing["char_start"], missing["char_end"]), (None, None, None)
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

    def test_qa_numbering_follows_first_valid_footnote_in_the_body(self):
        class FootnoteModel:
            async def ainvoke(self, _messages):
                return AIMessage(
                    content='{"answer":"先核对期限。[2] 再核对签收。[1] 同一条再次使用。[2][9]","citations":[1,2,3,9]}'
                )

        async def search(_query, **_context):
            return [
                Citation(document_id=key, knowledge_base_chunk_id=key, quoted_text="候选法条")
                for key in ("signed", "deadline", "unused")
            ]

        app = create_app(Settings(service_token="fixture-key"), search_laws=search, model=FootnoteModel())
        with TestClient(app) as client:
            response = client.post(
                "/internal/qa", headers=self.headers, json={"question": "要核对哪些内容？"}
            )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(answer["answer"], "先核对期限。[1] 再核对签收。[2] 同一条再次使用。[1]")
        self.assertEqual(
            [citation["document_id"] for citation in answer["citations"]], ["deadline", "signed"]
        )

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
                    self.assertNotIn("未找到直接法律依据", answer["answer"])
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
        self.assertNotIn("未找到直接法律依据", response.json()["answer"])
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
