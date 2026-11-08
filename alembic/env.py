import os
import sys
from logging.config import fileConfig

import alembic.context as context
from sqlalchemy import engine_from_config, pool, text

# Ensure app is discoverable on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser treats percent signs as interpolation markers; escape URL-encoded credentials.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    if settings.DATABASE_URL.startswith("postgresql"):
        connect_args = {"connect_timeout": settings.DB_CONNECT_TIMEOUT}
    else:
        connect_args = {}
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        postgres_lock_acquired = connection.dialect.name == "postgresql"
        if postgres_lock_acquired:
            connection.execute(text("SELECT pg_advisory_lock(724169203821)"))

        try:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
        finally:
            if postgres_lock_acquired:
                connection.execute(text("SELECT pg_advisory_unlock(724169203821)"))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
