import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import Base, engine
from app.core.errors import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.limiter import limiter
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.routers import api_v1_router, health_router
from app.services.nlp_service import warmup_model

logger = logging.getLogger("resumefit")
ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize tables if in dev/sqlite
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    
    # Pre-warm embedding model (Item 63: load at startup, not lazily on request)
    logger.info("Pre-warming NLP embedding model...")
    warmup_model()
    logger.info("Application ready to accept traffic.")
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready NLP resume and job-matching platform",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
)

# Rate limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global unified error handlers (Item 14)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Security and Observability Middleware (Items 37, 38, 86)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Route registrations (Item 15 & 85)
app.include_router(health_router)
app.include_router(api_v1_router)

# Mount static web UI assets
static_dir = ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    index_file = ROOT / "static" / "index.html"
    return FileResponse(index_file)
