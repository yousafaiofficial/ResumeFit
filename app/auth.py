"""Backwards-compatible password and current-user imports."""

from app.core.security import (
    get_current_user as current_user,
)
from app.core.security import (
    hash_password,
    verify_password,
)
from app.models.user import User

__all__ = ["hash_password", "verify_password", "current_user", "User"]
