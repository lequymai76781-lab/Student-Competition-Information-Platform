from functools import lru_cache
from typing import Self
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "Student Competition Intelligence Platform"
    api_prefix: str = "/api"
    database_url: str = Field(
        default="postgresql+psycopg://competition:competition@localhost:5432/competition_intelligence",
        validation_alias="DATABASE_URL",
    )
    backend_cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="BACKEND_CORS_ORIGINS",
    )
    app_secret: str = Field(
        default="v09-local-dev-secret-change-me",
        validation_alias="APP_SECRET",
    )
    beta_invite_code: str | None = Field(default=None, validation_alias="BETA_INVITE_CODE")
    frontend_url: str | None = Field(default=None, validation_alias="FRONTEND_URL")
    backend_url: str | None = Field(default=None, validation_alias="BACKEND_URL")
    log_dir: str | None = Field(default=None, validation_alias="LOG_DIR")

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        if self.environment in {"production", "staging", "beta"}:
            if self.app_secret == "v09-local-dev-secret-change-me" or len(self.app_secret) < 24:
                raise ValueError("APP_SECRET 必须通过环境变量提供且长度>=24（生产环境禁止默认Secret）")
            if self.database_url.startswith("sqlite:///"):
                raise ValueError("生产环境 DATABASE_URL 禁止使用本地 SQLite 文件")
            if self.beta_invite_code in (None, ""):
                raise ValueError("生产/Beta 环境必须配置 BETA_INVITE_CODE 以关闭公开注册")
            if not self.frontend_url or not self.backend_url:
                raise ValueError("生产/Beta 环境必须配置 FRONTEND_URL 与 BACKEND_URL")
            if "localhost" in self.backend_cors_origins:
                raise ValueError("生产环境 BACKEND_CORS_ORIGINS 禁止包含 localhost")
        return self

    @property
    def resolved_log_dir(self) -> str:
        if self.log_dir:
            return self.log_dir
        return str(Path(__file__).resolve().parents[3] / "data" / "logs")
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    meilisearch_url: str | None = Field(default=None, validation_alias="MEILISEARCH_URL")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    freshness_registration_open_hours: int = Field(default=24, validation_alias="FRESHNESS_REGISTRATION_OPEN_HOURS")
    freshness_submission_open_hours: int = Field(default=48, validation_alias="FRESHNESS_SUBMISSION_OPEN_HOURS")
    freshness_upcoming_hours: int = Field(default=72, validation_alias="FRESHNESS_UPCOMING_HOURS")
    freshness_finished_hours: int = Field(default=720, validation_alias="FRESHNESS_FINISHED_HOURS")
    freshness_unknown_hours: int = Field(default=168, validation_alias="FRESHNESS_UNKNOWN_HOURS")
    freshness_stale_multiplier: float = Field(default=2.0, validation_alias="FRESHNESS_STALE_MULTIPLIER")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
