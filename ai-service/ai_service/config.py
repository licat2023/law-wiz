"""Read inference and read-only knowledge base settings from the environment."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    environment: Literal["development", "testing", "production"] = "development"
    service_token: str = Field(repr=False, min_length=1)
    allow_fake_model: bool = False
    model_api_key: str = Field(default="", repr=False)
    model_base_url: str = ""
    model_name: str = ""
    model_timeout_seconds: float = Field(default=60, gt=0, le=300)
    max_concurrent: int = Field(default=2, ge=1)
    knowledge_base_base_url: str = ""
    knowledge_base_service_key: str = Field(default="", repr=False)
    knowledge_base_default_id: str = ""
