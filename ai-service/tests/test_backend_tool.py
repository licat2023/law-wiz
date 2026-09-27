import unittest
from unittest.mock import patch

import httpx
from app.core.config import settings
from app.tools.backend import BackendClient, BackendClientError, LawRetrievalTool


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> object:
        return self._payload


class _Client:
    def __init__(self, response: _Response | None = None, error: Exception | None = None, **kwargs) -> None:
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, path: str, **kwargs) -> _Response:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


class BackendClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._base_url = settings.backend_base_url
        self._token = settings.backend_token
        settings.backend_base_url = "configured-for-test"
        settings.backend_token = "test-service-token"

    def tearDown(self) -> None:
        settings.backend_base_url = self._base_url
        settings.backend_token = self._token

    async def test_law_tool_returns_structured_citations(self) -> None:
        response = _Response(
            200,
            {
                "code": 0,
                "request_id": "law-tool-test",
                "data": {
                    "items": [
                        {
                            "document_id": "1",
                            "chunk_id": "2",
                            "law_name": "测试法",
                            "article_no": "第一条",
                            "content": "测试法条内容",
                            "score": 0.9,
                        }
                    ]
                },
            },
        )
        with patch("app.tools.backend.httpx.AsyncClient", lambda **kwargs: _Client(response, **kwargs)):
            citations = await LawRetrievalTool().search(
                "测试问题", request_id="law-tool-test", trace_id="trace-law-tool"
            )

        self.assertEqual(citations[0].document_id, "1")
        self.assertEqual(citations[0].quoted_text, "测试法条内容")

    async def test_client_converts_timeout_non_success_and_invalid_schema(self) -> None:
        cases = (
            _Client(error=httpx.TimeoutException("timeout")),
            _Client(_Response(503, {"code": 50300})),
            _Client(_Response(200, {"unexpected": True})),
        )
        for client in cases:
            with self.subTest(client=client), patch(
                "app.tools.backend.httpx.AsyncClient", lambda _client=client, **kwargs: _client
            ), self.assertRaises(BackendClientError):
                await BackendClient().retrieve_laws(query="测试问题", request_id="law-tool-error", trace_id=None)
