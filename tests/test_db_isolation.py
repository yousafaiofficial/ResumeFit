from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_DATABASES = {
    PROJECT_ROOT / "app.db",
    PROJECT_ROOT / "test.db",
    *PROJECT_ROOT.glob("*.db.backup*"),
}


def test_test_database_is_in_pytest_temporary_directory(test_engine, test_db_path):
    actual_path = Path(test_engine.url.database).resolve()

    assert actual_path == test_db_path.resolve()
    assert actual_path.exists()
    assert actual_path.name == "test.sqlite3"
    assert actual_path not in {path.resolve() for path in PROTECTED_DATABASES}
    assert not actual_path.is_relative_to(PROJECT_ROOT)
