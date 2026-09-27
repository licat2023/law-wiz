"""AI-Service 配置：令牌只从环境读取，绝不写入日志或代码。"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AI_SERVICE_", extra="ignore")
    # Backend 地址属于部署连接信息，只能由环境变量提供。
    backend_base_url: str = ""
    backend_token: str = ""
    # 合同审查包含两次结构化模型调用；10 秒会使正常推理误判为不可用。
    # 部署环境仍可通过 AI_SERVICE_REQUEST_TIMEOUT_SECONDS 覆盖。
    request_timeout_seconds: float = 60.0
    # 真实密钥只由操作系统环境变量提供；绝不写入日志或仓库。
    deepseek_api_key: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY", "AI_SERVICE_DEEPSEEK_API_KEY")
    )
    deepseek_base_url: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "AI_SERVICE_DEEPSEEK_BASE_URL")
    )
    deepseek_model: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_MODEL", "AI_SERVICE_DEEPSEEK_MODEL")
    )


settings = Settings()
