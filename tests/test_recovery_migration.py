import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.mark.parametrize("previous_revision", [None, "phase12_sessions"])
def test_recovery_migration_on_disposable_database(tmp_path, previous_revision):
    path = tmp_path / "migration.sqlite3"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{path.as_posix()}",
        "SECRET_KEY": "migration-test-only-secret-at-least-32-characters",  # pragma: allowlist secret
    }
    root = Path(__file__).resolve().parents[1]
    if previous_revision:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", previous_revision],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            timeout=30,
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        timeout=30,
    )
    engine = create_engine(env["DATABASE_URL"])
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "auth_recovery_google"
            )
        inspector = inspect(engine)
        assert {"google_identities", "auth_challenges", "users", "user_sessions"} <= set(
            inspector.get_table_names()
        )
        assert inspector.get_foreign_keys("google_identities")[0]["referred_table"] == "users"
        assert inspector.get_pk_constraint("auth_challenges")["constrained_columns"] == [
            "token_hash"
        ]
    finally:
        engine.dispose()
