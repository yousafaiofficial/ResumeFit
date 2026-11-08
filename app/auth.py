"""Backwards compatibility shim for legacy auth imports."""

from app.core.security import (
    get_current_user as current_user,
)
from app.core.security import (
    hash_password,
    verify_password,
)
from app.core.security import (
    make_access_token as make_token,
)
from app.models.user import User

__all__ = ["hash_password", "verify_password", "make_token", "current_user", "User"]
