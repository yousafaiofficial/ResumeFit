import re
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
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
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_CONNECT_TIMEOUT: int = 10
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"

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

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL.") from exc

        if url.get_backend_name() not in {"sqlite", "postgresql"}:
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL.")
        if url.get_backend_name() == "sqlite" and url.drivername not in {
            "sqlite",
            "sqlite+pysqlite",
        }:
            raise ValueError("SQLite DATABASE_URL must use the synchronous pysqlite driver.")
        if url.get_backend_name() == "postgresql":
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+psycopg")
            elif url.drivername != "postgresql+psycopg":
                raise ValueError("PostgreSQL DATABASE_URL must use the psycopg 3 driver.")
        return url.render_as_string(hide_password=False)

    @field_validator("FORWARDED_ALLOW_IPS")
    @classmethod
    def validate_forwarded_allow_ips(cls, value: str) -> str:
        trusted_proxies = [address.strip() for address in value.split(",")]
        try:
            for address in trusted_proxies:
                ip_address(address)
        except ValueError as exc:
            raise ValueError(
                "FORWARDED_ALLOW_IPS must contain explicit proxy IP addresses; wildcards are unsafe."
            ) from exc
        return ",".join(trusted_proxies)

    @model_validator(mode="after")
    def validate_production_configuration(self):
        if (
            self.DB_POOL_SIZE < 1
            or self.DB_MAX_OVERFLOW < 0
            or self.DB_POOL_TIMEOUT < 1
            or self.DB_POOL_RECYCLE < 1
            or self.DB_CONNECT_TIMEOUT < 1
        ):
            raise ValueError(
                "Database pool size and timeouts must be positive; "
                "max overflow must be non-negative."
            )

        if self.is_production():
            if re.search(r"(dev|test|example|change.?me|replace)", self.SECRET_KEY, re.IGNORECASE):
                raise ValueError(
                    "Production SECRET_KEY must not be a development or example value."
                )
            if make_url(self.DATABASE_URL).get_backend_name() != "postgresql":
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
                    or "*" in origin.hostname
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
                or any("*" in host for host in self.ALLOWED_HOSTS)
            ):
                raise ValueError(
                    "Production ALLOWED_HOSTS must be explicitly configured without wildcards."
                )
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
