"""DeepSeek 的 LangChain OpenAI-compatible 封装。"""

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


class DeepSeekConfigurationError(RuntimeError):
    """真实模型配置不完整时的明确错误；不包含任何密钥内容。"""


class DeepSeekInvocationError(RuntimeError):
    """模型网络、超时或厂商响应错误的统一领域错误。"""


logger = logging.getLogger(__name__)


def create_chat_model() -> BaseChatModel:
    """按需创建 ChatOpenAI，避免测试/导入阶段读取或触碰外部网络。"""
    if not settings.deepseek_api_key or not settings.deepseek_base_url or not settings.deepseek_model:
        raise DeepSeekConfigurationError("DeepSeek 配置不完整")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout=settings.request_timeout_seconds,
        max_retries=1,
    )


async def invoke_chat(model, payload):
    """统一转换厂商异常；日志只记录异常类型，绝不记录请求头或密钥。"""
    try:
        return await model.ainvoke(payload)
    except Exception as exc:
        logger.warning("DeepSeek invocation failed: %s", type(exc).__name__)
        raise DeepSeekInvocationError("DeepSeek 服务暂不可用") from exc
