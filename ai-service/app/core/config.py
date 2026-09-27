"""AI-Service 配置：令牌只从环境读取，绝不写入日志或代码。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AI_SERVICE_", extra="ignore")
    # Backend 地址属于部署连接信息，只能由环境变量提供。
    backend_base_url: str = ""
    backend_token: str = ""
    request_timeout_seconds: float = 10.0


settings = Settings()
