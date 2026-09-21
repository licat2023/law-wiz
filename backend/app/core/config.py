"""应用配置。

原则：
- **凭据只从环境变量（或 .env）读取**，绝不写死在代码里（见 02-技术栈 §4.2）。
- 所有配置项都有安全默认值，使"克隆即可跑"成立；**生产环境的差异由环境变量覆盖**。
- 不引入任何网络请求或副作用，纯读取。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LAWWIZ_",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 运行环境 ----------
    app_env: Literal["development", "testing", "production"] = "development"
    app_name: str = "智法宝"
    api_prefix: str = "/api/v1"
    debug: bool = False

    # 若为 True，注册接口接受固定验证码（见 05-接口设计 §8）。
    # ⚠️ production 下必须为 False —— 由启动期校验强制（见 main.py）。
    allow_fixed_verify_code: bool = True

    # ---------- 数据库 ----------
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "lawwiz"
    # ⚠️ 必须与 deploy/docker-compose.dev.yml 的 `MYSQL_PASSWORD` 默认值一致，
    # 否则"起容器 + 跑应用"会报 1045 Access denied，而 /health 只回报
    # database: unavailable（原因见 05-接口设计 §5.7 的说明）。
    # 生产环境由 docker-compose.prod.yml 强制从 .env 注入，不用本默认值。
    db_password: str = "changeme"
    db_name: str = "law_wiz"
    # 服务器内存极紧（1.7 GiB，可用约 950 MiB），池要小
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # ---------- Redis（刷新令牌、限流计数）----------
    redis_url: str = "redis://127.0.0.1:6379/0"
    refresh_token_ttl_seconds: int = 7 * 24 * 3600
    redis_key_prefix: str = "lawwiz:"

    # ---------- 令牌 ----------
    # 生产必须通过环境变量覆盖；开发默认值仅用于本地跑通
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 30 * 60

    # ---------- 文件存储（内容寻址）----------
    storage_backend: Literal["local", "minio"] = "local"
    # ⚠️ 这是**根目录**，不是"文件目录"：实际路径 = 根目录 + object_key，
    # 而 object_key 本身已含 `files/` 前缀（04-数据库设计 §4.1，该约定同时用于 MinIO）。
    # 若此处写成 `./.data/files`，就会得到 `.data/files/files/xx/<hash>` 的重复层级。
    storage_local_root: str = "./.data"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "lawwiz"
    minio_secure: bool = False
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MB，对应 01-需求说明书 §3.3

    # ---------- 向量存储（M2/M3 的 AI 底座）----------
    # 一期为进程内 Chroma，不单独起容器（省一个容器的内存）
    vector_backend: Literal["chroma", "memory"] = "memory"
    chroma_path: str = "./.data/chroma"
    chroma_collection: str = "law_knowledge"

    # ---------- 外部能力 ----------
    # 一期接云端 OCR API（服务器跑不动本地 OCR，见 ADR-0003 与容量约束文档）
    ocr_provider: Literal["stub", "cloud"] = "stub"
    ocr_api_base: str = ""
    ocr_api_key: str = ""

    # `fake` 返回确定性的占位结论，**仅供开发与演示** —— 它让整条审查/问答链路
    # 在不接真实模型、不需要 API key 的情况下可以完整跑通。
    # 生产环境由启动期校验强制禁用（见 main.py），因为它会产出**假的风险结论**。
    llm_provider: Literal["stub", "fake", "deepseek", "ollama"] = "stub"
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 1  # 结构化输出解析失败时的重试次数（见 03-概要设计 §5.3）

    embedding_provider: Literal["stub", "cloud"] = "stub"
    embedding_api_base: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 1024

    # ---------- 限流（见 05-接口设计 §4.5）----------
    # 认证类按 **IP** 计数（防暴力破解），其余按**用户**计数
    rate_limit_auth_per_minute: int = 10
    rate_limit_ai_per_minute: int = 10
    rate_limit_read_per_minute: int = 120
    # 轮询任务状态单独一档：前端轮询间隔最小 1 秒，60/分足够且能挡住死循环
    rate_limit_poll_per_minute: int = 60

    # ---------- 跨域 ----------
    # 生产由 OpenResty 同源代理，不开启宽泛 CORS（见 05-接口设计 §8）
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ---------- 派生属性 ----------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内单例。避免每次依赖注入都重新读取 .env。"""
    return Settings()
