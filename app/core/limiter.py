from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

# In production with REDIS_URL, slowapi can use Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL or "memory://",
    default_limits=["100/minute"],
)
