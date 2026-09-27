import json
import unittest

from app.agent.exceptions import AgentNotFoundError
from app.api.exception_handlers import agent_not_found_handler
from app.main import app
from fastapi import Request


class AgentNotFoundHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_return_structured_404_response(self):
        request = Request({"type": "http", "method": "POST", "path": "/"})

        response = await agent_not_found_handler(
            request,
            AgentNotFoundError("missing"),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            json.loads(response.body),
            {
                "success": False,
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": "Agent not found: missing",
                    "agentCode": "missing",
                },
            },
        )

    def test_should_register_handler_on_application(self):
        self.assertIs(app.exception_handlers[AgentNotFoundError], agent_not_found_handler)
