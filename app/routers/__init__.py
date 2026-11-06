from app.routers.api_v1 import api_v1_router
from app.routers.api_v1.health import router as health_router

__all__ = ["api_v1_router", "health_router"]
