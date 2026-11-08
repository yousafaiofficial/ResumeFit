import hashlib
import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

# Keep imports of the application away from developer and production databases.
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-chars-long!"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

database_module = importlib.import_module("app.core.database")
main_module = importlib.import_module("app.main")
security_module = importlib.import_module("app.core.security")
limiter_module = importlib.import_module("app.core.limiter")
user_module = importlib.import_module("app.models.user")
Base = database_module.Base
get_db = database_module.get_db
hash_password = security_module.hash_password
create_user_session = security_module.create_user_session
User = user_module.User
app = main_module.app
limiter = limiter_module.limiter

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_database_snapshots() -> dict[Path, bytes]:
    return {
        path: hashlib.sha256(path.read_bytes()).digest()
        for path in PROJECT_ROOT.glob("*.db*")
        if path.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def protect_project_databases():
    snapshots = _project_database_snapshots()
    yield
    assert _project_database_snapshots() == snapshots, (
        "A project database or backup changed during the test run."
    )


@pytest.fixture(autouse=True)
def isolate_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def test_db_path(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture
def test_engine(test_db_path):
    engine = create_engine(
        URL.create("sqlite", database=str(test_db_path)),
        connect_args={"check_same_thread": False},
    )
    previous_database_engine = database_module.engine
    previous_main_engine = main_module.engine
    database_module.engine = engine
    main_module.engine = engine

    try:
        Base.metadata.create_all(bind=engine)
        yield engine
    finally:
        try:
            Base.metadata.drop_all(bind=engine)
        finally:
            try:
                engine.dispose()
            finally:
                database_module.engine = previous_database_engine
                main_module.engine = previous_main_engine


@pytest.fixture
def db_session(test_engine):
    session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    previous_overrides = app.dependency_overrides.copy()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def pre_auth_headers(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {
        "Origin": "http://localhost:8000",
        "X-CSRF-Token": response.json()["csrf_token"],
    }


@pytest.fixture
def test_user_a(db_session):
    user = User(
        email="usera@example.com",
        password_hash=hash_password("Password1234!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_b(db_session):
    user = User(
        email="userb@example.com",
        password_hash=hash_password("Password5678!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _session_headers(db_session, user):
    _, session_token, csrf_token = create_user_session(db_session, user)
    return {
        "Cookie": f"{database_module.settings.session_cookie_name}={session_token}",
        "X-CSRF-Token": csrf_token,
        "Origin": "http://localhost:8000",
    }


@pytest.fixture
def auth_headers_user_a(db_session, test_user_a):
    return _session_headers(db_session, test_user_a)


@pytest.fixture
def auth_headers_user_b(db_session, test_user_b):
    return _session_headers(db_session, test_user_b)
