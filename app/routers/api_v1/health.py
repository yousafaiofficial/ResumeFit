import datetime as dt

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.database import check_db_health
from app.schemas.common import HealthResponse, ReadinessResponse
from app.services.nlp_service import is_model_ready

router = APIRouter(tags=["Health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe: verifies process is active."""
    return HealthResponse(
        status="ok",
        timestamp=dt.datetime.now(dt.UTC).isoformat(),
        version="0.2.0",
        app_env=settings.APP_ENV,
    )


@router.get("/readyz", response_model=ReadinessResponse)
def readyz(response: Response):
    """Readiness probe: verifies database connectivity and ML engine readiness."""
    db_ok = check_db_health()
    model_ok = is_model_ready()
    is_ready = db_ok and model_ok

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        database=db_ok,
        nlp_model_loaded=model_ok,
    )
