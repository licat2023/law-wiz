import unittest

from app.agent.contract_review.agent import ContractReviewAgent
from app.agent.legal_qa.agent import LegalQaAgent
from app.agent.registry import AgentRegistry
from app.agent.runtime import AgentRuntime
from app.main import app
from app.schemas.contracts import AgentContext, Citation
from fastapi.testclient import TestClient


class _LawTool:
    async def search(self, query: str, *, request_id: str, trace_id: str | None) -> list[Citation]:
        return [
            Citation(
                document_id="law-1",
                kb_chunk_id="chunk-1",
                law_name="测试法",
                article_no="第一条",
                quoted_text="测试法条内容",
                relevance_score=0.9,
            ),
            # 缺少可追溯内容的来源不得被返回给 Backend 持久化。
            Citation(document_id="law-2", kb_chunk_id="chunk-2"),
        ]


class _RiskRuleTool:
    async def match(self, plain_text: str, *, request_id: str, trace_id: str | None) -> list[dict]:
        return [
            {
                "risk_level": "high",
                "description": "测试风险规则命中。",
                "source_type": "rule",
            }
        ]


class LegalQaAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_registry_and_runtime_invoke_legal_qa(self):
        registry = AgentRegistry()
        self.assertIsNotNone(registry.get("legal_qa"))

        result = await AgentRuntime(registry).invoke(
            agent_code="legal_qa",
            input={"question": "违约金过高能调整吗？"},
            context=AgentContext(requestId="legal-qa-runtime"),
        )

        self.assertIn("未找到直接法律依据", result.answer)
        self.assertEqual(result.citations, [])

    async def test_graph_validates_untraceable_citations(self):
        result = await LegalQaAgent(_LawTool()).invoke(
            {"question": "测试问题"},
            AgentContext(requestId="legal-qa-graph", traceId="trace-legal-qa"),
        )

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0].document_id, "law-1")

    async def test_contract_review_graph_returns_rule_risk_points(self):
        result = await ContractReviewAgent(_LawTool(), _RiskRuleTool()).invoke(
            {"plain_text": "测试合同文本"}, AgentContext(requestId="contract-review-graph")
        )

        self.assertEqual(result.extracted_terms["text_length"], len("测试合同文本"))
        self.assertEqual(result.risk_points[0].source_type, "rule")


class AgentInvokeApiTest(unittest.TestCase):
    def test_invoke_legal_qa_uses_common_agent_api(self):
        response = TestClient(app).post(
            "/api/v1/agent/invoke",
            json={
                "agentCode": "legal_qa",
                "input": {"question": "合同违约金如何处理？"},
                "context": {"requestId": "legal-qa-api", "userId": "1", "sessionId": "2"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requestId"], "legal-qa-api")
        self.assertIn("answer", response.json()["data"])
