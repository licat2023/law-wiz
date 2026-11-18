"""显式配置的 OpenAI-compatible LangChain 模型接入。"""

import logging
from contextlib import aclosing

from langchain_core.language_models.chat_models import BaseChatModel


class DeepSeekConfigurationError(RuntimeError):
    """模型配置不完整。"""


class DeepSeekInvocationError(RuntimeError):
    """模型网络、超时或响应错误。"""


logger = logging.getLogger(__name__)


def create_chat_model(*, api_key: str, base_url: str, model: str, timeout: float = 60) -> BaseChatModel:
    """用显式连接参数创建模型客户端，单次调用由配置超时限制，客户端重试已关闭。"""
    if not api_key or not base_url or not model:
        raise DeepSeekConfigurationError("模型配置不完整")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(api_key=api_key, base_url=base_url, model=model, timeout=timeout, max_retries=0)


async def invoke_chat(model, payload):
    """异步调用模型；异常记录类型并统一包装为 `DeepSeekInvocationError`。"""
    try:
        return await model.ainvoke(payload)
    except Exception as exc:
        logger.warning("Model invocation failed: %s", type(exc).__name__)
        raise DeepSeekInvocationError("模型服务暂不可用") from exc


async def stream_chat(model, payload):
    """Yield model chunks and close the upstream stream on cancellation."""
    try:
        async with aclosing(model.astream(payload)) as chunks:
            async for chunk in chunks:
                yield chunk
    except Exception as exc:
        logger.warning("Model stream failed: %s", type(exc).__name__)
        raise DeepSeekInvocationError("模型服务暂不可用") from exc
