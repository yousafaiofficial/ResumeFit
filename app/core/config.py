import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "ResumeFit"
    APP_ENV: Literal["dev", "test", "staging", "prod"] = "dev"
    DEBUG: bool = False

    SECRET_KEY: str = Field(..., min_length=32)
    SESSION_EXPIRE_DAYS: int = 7
    PREAUTH_CSRF_EXPIRE_SECONDS: int = 600

    # Database & Cache
    DATABASE_URL: str = "sqlite:///./app.db"
    REDIS_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True
    DB_POOL_TIMEOUT: int = 30

    # Cookie & Security
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax"] = "lax"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver"]

    # Input Limits (Hard Caps)
    MAX_PDF_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_PDF_PAGES: int = 10
    MAX_JOB_DESC_CHARS: int = 10000
    MIN_JOB_DESC_CHARS: int = 60
    MAX_RESUME_CHARS: int = 30000
    MIN_RESUME_CHARS: int = 80

    # Rate Limiting
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    RATE_LIMIT_ANALYZE: str = "10/minute"

    # ML & LLM Settings
    EMBED_MODEL: str = "all-MiniLM-L6-v2"
    ANTHROPIC_API_KEY: str | None = None
    LLM_MODEL: str = "claude-sonnet-5-5"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "SECRET_KEY must be explicitly configured with at least 32 characters."
            )
        return value

    @model_validator(mode="after")
    def validate_production_configuration(self):
        if self.is_production():
            if re.search(r"(dev|test|example|change.?me|replace)", self.SECRET_KEY, re.IGNORECASE):
                raise ValueError(
                    "Production SECRET_KEY must not be a development or example value."
                )
            if not self.DATABASE_URL.startswith(("postgresql://", "postgresql+")):
                raise ValueError(
                    "Production requires PostgreSQL; SQLite is for local development and tests."
                )
            parsed_origins = [urlsplit(origin) for origin in self.ALLOWED_ORIGINS]
            if (
                "ALLOWED_ORIGINS" not in self.model_fields_set
                or not parsed_origins
                or any(
                    origin.scheme != "https"
                    or not origin.hostname
                    or origin.path not in ("", "/")
                    or origin.username is not None
                    or origin.password is not None
                    for origin in parsed_origins
                )
            ):
                raise ValueError(
                    "Production ALLOWED_ORIGINS must be explicitly configured with HTTPS origins."
                )
            if (
                "ALLOWED_HOSTS" not in self.model_fields_set
                or not self.ALLOWED_HOSTS
                or "*" in self.ALLOWED_HOSTS
            ):
                raise ValueError("Production ALLOWED_HOSTS must be explicitly configured.")
        if self.SESSION_EXPIRE_DAYS < 1 or self.PREAUTH_CSRF_EXPIRE_SECONDS < 1:
            raise ValueError("Session and pre-authentication CSRF lifetimes must be positive.")
        return self

    def is_production(self) -> bool:
        return self.APP_ENV in ("staging", "prod")

    @property
    def session_cookie_name(self) -> str:
        return "__Host-resumefit_session" if self.is_production() else "resumefit_session"

    @property
    def csrf_cookie_name(self) -> str:
        return (
            "__Host-resumefit_pre_auth_csrf" if self.is_production() else "resumefit_pre_auth_csrf"
        )

    @property
    def secure_cookies(self) -> bool:
        return self.is_production() or self.COOKIE_SECURE


settings = Settings()  # type: ignore[call-arg]  # BaseSettings reads required secrets from env/.env.
if settings.is_production():
    settings.DEBUG = False
