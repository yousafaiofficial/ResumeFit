import json
import os
import secrets
from typing import Literal
from pydantic import Field, field_validator
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
    
    # Primary signing secret
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    # Secondary/Previous signing secret for key rotation
    PREVIOUS_SECRET_KEY: str | None = None
    JWT_ACTIVE_KID: str = "key-primary"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database & Cache
    DATABASE_URL: str = "sqlite:///./app.db"
    REDIS_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True
    DB_POOL_TIMEOUT: int = 30

    # Cookie & Security
    COOKIE_NAME: str = "resumefit_session"
    CSRF_COOKIE_NAME: str = "resumefit_csrf"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

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
    def validate_secret_key(cls, v: str, info) -> str:
        values = info.data
        env = values.get("APP_ENV", "dev")
        if env in ("staging", "prod"):
            if not v or "change-me" in v.lower() or len(v) < 32:
                raise ValueError(
                    f"Production/staging environment requires a strong SECRET_KEY (at least 32 characters, non-default). Found: {v[:8]}..."
                )
        return v

    def is_production(self) -> bool:
        return self.APP_ENV in ("staging", "prod")

    @property
    def jwt_verification_keys(self) -> dict[str, str]:
        """Returns dict of key_id -> secret for zero-downtime key rotation."""
        keys = {self.JWT_ACTIVE_KID: self.SECRET_KEY}
        if self.PREVIOUS_SECRET_KEY:
            keys["key-previous"] = self.PREVIOUS_SECRET_KEY
        return keys


settings = Settings()
if settings.is_production():
    settings.COOKIE_SECURE = True
    settings.DEBUG = False
