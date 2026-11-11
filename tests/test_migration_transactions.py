"""Exercise the migration environment without touching application databases."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import alembic.context as context
import pytest
import sqlalchemy
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text


@pytest.mark.parametrize("migration_fails", [False, True])
def test_migration_environment_owns_transaction_and_releases_lock(monkeypatch, migration_fails):
    engine = create_engine("sqlite://")
    with engine.begin() as setup:
        setup.execute(text("CREATE TABLE migration_probe (id INTEGER)"))

    locks = []
    state = {}

    class LockConnection:
        dialect = SimpleNamespace(name="postgresql")

        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection.close()

        def execute(self, statement):
            locks.append(str(statement))
            # Emulate the transaction started by PostgreSQL lock queries.
            return self.connection.execute(text("SELECT 1"))

        def commit(self):
            self.connection.commit()

        def rollback(self):
            self.connection.rollback()

    def configure(*, connection, **kwargs):
        assert not connection.connection.in_transaction()
        state["connection"] = connection.connection
        state["context"] = MigrationContext.configure(
            connection.connection, opts={"transactional_ddl": True}
        )

    def migrate():
        state["connection"].execute(text("INSERT INTO migration_probe VALUES (1)"))
        if migration_fails:
            raise RuntimeError("simulated migration failure")

    config = MagicMock()
    config.config_file_name = None
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", lambda: state["context"].begin_transaction())
    monkeypatch.setattr(context, "run_migrations", migrate)
    monkeypatch.setattr(
        sqlalchemy,
        "engine_from_config",
        lambda *args, **kwargs: SimpleNamespace(connect=lambda: LockConnection(engine.connect())),
    )
    path = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    try:
        if migration_fails:
            with pytest.raises(RuntimeError, match="simulated migration failure"):
                runpy.run_path(str(path))
        else:
            runpy.run_path(str(path))
        with engine.connect() as verification:
            assert verification.scalar(text("SELECT COUNT(*) FROM migration_probe")) == (
                0 if migration_fails else 1
            )
        assert len(locks) == 2
        assert "pg_advisory_lock(" in locks[0]
        assert "pg_advisory_unlock(" in locks[1]
    finally:
        engine.dispose()
