import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_postgresql_urls_use_psycopg_driver_and_escape_password():
    settings = Settings(
        DATABASE_URL="postgresql://resumefit:p%40ss%25word@db.example/resumefit",  # pragma: allowlist secret
    )
    url = make_url(settings.DATABASE_URL)

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss%word"  # pragma: allowlist secret


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql://user:password@localhost/resumefit",  # pragma: allowlist secret
        "not-a-database-url",
        "postgresql+psycopg2://user:password@localhost/resumefit",  # pragma: allowlist secret
        "sqlite+aiosqlite:///./app.db",
    ],
)
def test_unsupported_database_urls_are_rejected(database_url):
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL=database_url)


def test_database_url_validation_errors_hide_credentials():
    with pytest.raises(ValidationError) as error:
        Settings(
            DATABASE_URL="mysql://user:do-not-log-this@db.example/resumefit",  # pragma: allowlist secret
        )

    assert "do-not-log-this" not in str(error.value)


def test_production_rejects_sqlite():
    with pytest.raises(ValidationError, match="requires PostgreSQL"):
        Settings(
            APP_ENV="prod",
            SECRET_KEY="random-production-signing-key-with-adequate-entropy-123456",  # pragma: allowlist secret
            DATABASE_URL="sqlite:///./app.db",
            ALLOWED_ORIGINS=["https://resumefit.example"],
            ALLOWED_HOSTS=["resumefit.example"],
        )


def test_forwarded_proxy_wildcards_are_rejected():
    for forwarded_ips in ("*", "127.0.0.1,*", "proxy.example"):
        with pytest.raises(ValidationError, match="explicit proxy IP addresses"):
            Settings(FORWARDED_ALLOW_IPS=forwarded_ips)


@pytest.mark.parametrize(
    "field_values",
    [
        {"ALLOWED_HOSTS": ["*.resume.example", "127.0.0.1"]},
        {"ALLOWED_ORIGINS": ["https://*.resume.example"]},
    ],
)
def test_production_rejects_wildcard_origins_and_hosts(field_values):
    production_settings = {
        "APP_ENV": "prod",
        "SECRET_KEY": "random-production-signing-key-with-adequate-entropy-123456",  # pragma: allowlist secret
        "DATABASE_URL": "postgresql://resumefit:encoded%40password@db.example/resumefit",  # pragma: allowlist secret
        "ALLOWED_ORIGINS": ["https://resume.example"],
        "ALLOWED_HOSTS": ["resume.example", "127.0.0.1"],
    }

    with pytest.raises(ValidationError):
        Settings(**(production_settings | field_values))


@pytest.mark.parametrize(
    "pool_settings",
    [
        {"DB_POOL_SIZE": 0},
        {"DB_MAX_OVERFLOW": -1},
        {"DB_POOL_TIMEOUT": 0},
        {"DB_POOL_RECYCLE": 0},
        {"DB_CONNECT_TIMEOUT": 0},
    ],
)
def test_invalid_database_pool_settings_are_rejected(pool_settings):
    with pytest.raises(ValidationError, match="Database pool size and timeouts"):
        Settings(**pool_settings)
