from fastapi import APIRouter
from app.routers.api_v1.auth import router as auth_router
from app.routers.api_v1.analyze import router as analyze_router
from app.routers.api_v1.history import router as history_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(analyze_router)
api_v1_router.include_router(history_router)

__all__ = ["api_v1_router"]
