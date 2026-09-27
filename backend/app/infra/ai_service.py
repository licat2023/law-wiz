"""Backend 调用独立 AI-Service 的唯一适配器。"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode


class _InvokeResponse(BaseModel):
    requestId: str
    data: dict


class AiServiceClient:
    async def contract_review(
        self,
        *,
        plain_text: str,
        user_id: int,
        task_id: int,
        request_id: str,
        trace_id: str | None = None,
    ) -> dict:
        """调用通用 Agent API；Backend 不感知 ContractReviewGraph 的节点细节。"""
        return await self._invoke(
            agent_code="contract_review",
            input={"plain_text": plain_text},
            context={"userId": str(user_id), "taskId": str(task_id)},
            request_id=request_id,
            trace_id=trace_id,
        )

    async def legal_qa(
        self,
        *,
        question: str,
        user_id: int,
        session_id: int,
        request_id: str,
        trace_id: str | None = None,
    ) -> dict:
        return await self._invoke(
            agent_code="legal_qa",
            input={"question": question},
            context={"userId": str(user_id), "sessionId": str(session_id)},
            request_id=request_id,
            trace_id=trace_id,
        )

    async def _invoke(
        self,
        *,
        agent_code: str,
        input: dict,
        context: dict,
        request_id: str,
        trace_id: str | None,
    ) -> dict:
        settings = get_settings()
        if not settings.ai_service_base_url:
            raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 服务地址未配置")
        payload = {
            "agentCode": agent_code,
            "input": input,
            "context": {"requestId": request_id, "traceId": trace_id or request_id, **context},
        }
        headers = {"X-Request-ID": request_id, "X-Trace-ID": trace_id or request_id}
        try:
            async with httpx.AsyncClient(base_url=settings.ai_service_base_url, timeout=settings.ai_service_timeout_seconds) as client:
                response = await client.post("/api/v1/agent/invoke", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 服务响应超时") from exc
        except httpx.HTTPError as exc:
            raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 服务暂不可用") from exc
        if response.status_code == 404:
            raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "请求的 AI Agent 不存在")
        if not response.is_success:
            raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 服务调用失败")
        try:
            return _InvokeResponse.model_validate(response.json()).data
        except (ValidationError, ValueError) as exc:
            raise BusinessError(ErrorCode.LLM_BAD_RESPONSE, "AI 服务返回结构不合法") from exc
