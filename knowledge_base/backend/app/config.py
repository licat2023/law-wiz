"""读取 KB_ 环境配置，并在启动时校验知识库的运行依赖。"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """通过环境变量或 .env 读取配置，密码哈希、密钥与数据库地址在 repr 中省略。"""

    model_config = SettingsConfigDict(env_prefix="KB_", env_file=".env", extra="ignore")

    environment: Literal["development", "testing", "production"] = "development"
    database_url: str = Field(default="", repr=False)
    data_root: Path = Path(".data")
    admin_username: str = "admin"
    admin_password_hash: str = Field(default="", repr=False)
    admin_application_id: str = "law-wiz"
    jwt_secret: str = Field(default="", repr=False)
    jwt_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    service_keys_json: str = Field(default="{}", repr=False)
    embedding_mode: Literal["remote", "development"] = "remote"
    embedding_base_url: str = ""
    embedding_api_key: str = Field(default="", repr=False)
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=1536, ge=1, le=65536)
    request_timeout_seconds: float = Field(default=60, gt=0, le=300)
    worker_enabled: bool = True
    worker_poll_seconds: float = Field(default=1, gt=0, le=60)
    lease_seconds: int = Field(default=300, ge=10, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=10)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_text_chars: int = Field(default=2_000_000, ge=1, le=10_000_000)
    max_pdf_pages: int = Field(default=300, ge=1, le=1000)
    max_chunks: int = Field(default=10000, ge=1, le=50000)
    parent_context_chars: int = Field(default=8000, ge=500, le=50000)
    auto_create_schema: bool = False
    cors_origins: list[str] = []

    def check_runtime(self):
        """检查数据库、凭证及嵌入配置，并拦截生产环境禁用的模式。"""
        if not self.database_url:
            raise ValueError("需要配置 KB_DATABASE_URL")
        if not self.database_url.startswith(("mysql+aiomysql://", "sqlite+aiosqlite://")):
            raise ValueError("数据库必须使用异步驱动")
        if self.environment == "production" and not self.database_url.startswith("mysql+aiomysql://"):
            raise ValueError("生产数据库必须使用 mysql+aiomysql")
        if len(self.jwt_secret) < 32 or not self.admin_password_hash:
            raise ValueError("需要配置管理员密码哈希和至少 32 字符的 JWT 签名密钥")
        if self.embedding_mode == "development":
            if self.environment == "production":
                raise ValueError("生产环境不允许开发嵌入")
        elif not all((self.embedding_base_url, self.embedding_api_key, self.embedding_model)):
            raise ValueError("需要完整配置远程嵌入服务")
        if self.environment == "production" and self.auto_create_schema:
            raise ValueError("生产环境请使用显式数据库初始化命令")
