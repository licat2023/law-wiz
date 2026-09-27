import unittest

from app.agent.exceptions import AgentNotFoundError
from app.agent.registry import AgentRegistry
from app.agent.runtime import AgentRuntime
from app.schemas.contracts import AgentContext


class AgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = AgentRegistry()
        self.runtime = AgentRuntime(self.registry)

    def test_should_get_demo_agent_from_registry(self):
        agent = self.registry.get("demo")

        self.assertIsNotNone(agent)

    async def test_should_invoke_demo_agent(self):
        # Arrange
        # registry 和 runtime 已在 setUp() 中完成初始化

        # Act
        result = await self.runtime.invoke(
            agent_code="demo",
            input={"message": "runtime test", "scene": "CONNECTIVITY_TEST"},
            context=AgentContext(requestId="runtime-test"),
        )

        # Assert
        self.assertEqual(result["agent_name"], "DemoAgent")
        self.assertEqual(result["scene"], "CONNECTIVITY_TEST")

    async def test_should_raise_domain_error_for_unknown_agent(self):
        with self.assertRaisesRegex(AgentNotFoundError, "Agent not found: missing"):
            await self.runtime.invoke(
                agent_code="missing",
                input={},
                context=AgentContext(requestId="missing-agent"),
            )
