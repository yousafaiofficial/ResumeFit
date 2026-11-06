"""Backwards compatibility shim for legacy database imports."""
from app.core.database import Base, engine, SessionLocal, get_db
from app.models.user import User
from app.models.analysis import Analysis


def init_db():
    Base.metadata.create_all(engine)


__all__ = ["Base", "engine", "SessionLocal", "get_db", "init_db", "User", "Analysis"]
