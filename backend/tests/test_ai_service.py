"""Backend 与独立 AI-Service 的适配器和 Internal API 契约测试。"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra.ai_service import AiServiceClient


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

    async def post(self, path: str, **kwargs) -> _Response:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def _replace_http_client(monkeypatch, *, response: _Response | None = None, error: Exception | None = None) -> None:
    from app.infra import ai_service

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: _Client(response, error, **kwargs))


@pytest.mark.asyncio
async def test_ai_service_client_returns_valid_agent_result(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_service_base_url", "configured-for-test")
    _replace_http_client(
        monkeypatch,
        response=_Response(
            200,
            {"requestId": "qa-request", "data": {"answer": "测试回答", "citations": []}},
        ),
    )

    result = await AiServiceClient().legal_qa(
        question="测试问题", user_id=1, session_id=2, request_id="qa-request", trace_id="trace-request"
    )

    assert result == {"answer": "测试回答", "citations": []}


@pytest.mark.asyncio
async def test_ai_service_client_converts_timeout_and_connection_failure(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_service_base_url", "configured-for-test")
    for error in (httpx.TimeoutException("timeout"), httpx.ConnectError("offline")):
        _replace_http_client(monkeypatch, error=error)
        with pytest.raises(BusinessError) as raised:
            await AiServiceClient().legal_qa(question="测试", user_id=1, session_id=2, request_id="qa-request")
        assert raised.value.code == ErrorCode.LLM_UNAVAILABLE


@pytest.mark.asyncio
async def test_ai_service_client_rejects_non_success_and_invalid_schema(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_service_base_url", "configured-for-test")
    _replace_http_client(monkeypatch, response=_Response(502, {"detail": "bad gateway"}))
    with pytest.raises(BusinessError) as raised:
        await AiServiceClient().legal_qa(question="测试", user_id=1, session_id=2, request_id="qa-request")
    assert raised.value.code == ErrorCode.LLM_UNAVAILABLE

    _replace_http_client(monkeypatch, response=_Response(200, {"unexpected": True}))
    with pytest.raises(BusinessError) as raised:
        await AiServiceClient().legal_qa(question="测试", user_id=1, session_id=2, request_id="qa-request")
    assert raised.value.code == ErrorCode.LLM_BAD_RESPONSE


@pytest.mark.asyncio
async def test_ai_service_client_converts_agent_not_found(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_service_base_url", "configured-for-test")
    _replace_http_client(monkeypatch, response=_Response(404, {"error": {"code": "AGENT_NOT_FOUND"}}))

    with pytest.raises(BusinessError) as raised:
        await AiServiceClient().legal_qa(question="测试", user_id=1, session_id=2, request_id="qa-request")

    assert raised.value.code == ErrorCode.LLM_UNAVAILABLE
    assert raised.value.message == "请求的 AI Agent 不存在"


def test_internal_legal_qa_api_requires_service_token(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_service_token", "test-service-token")

    missing = client.get("/api/v1/internal/legal-qa/laws?q=违约金")
    invalid = client.get(
        "/api/v1/internal/legal-qa/laws?q=违约金",
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    accepted = client.get(
        "/api/v1/internal/legal-qa/laws?q=违约金",
        headers={"X-Internal-Service-Token": "test-service-token", "X-Request-ID": "internal-test-01"},
    )

    assert missing.status_code == 401
    assert missing.json()["code"] == int(ErrorCode.ACCESS_TOKEN_INVALID)
    assert invalid.status_code == 403
    assert invalid.json()["code"] == int(ErrorCode.FORBIDDEN)
    assert accepted.status_code == 200
    assert accepted.json()["code"] == 0
    assert accepted.json()["request_id"] == "internal-test-01"
