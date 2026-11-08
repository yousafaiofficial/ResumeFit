from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Any | None = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    app_env: str


class ReadinessResponse(BaseModel):
    status: str
    database: bool
    nlp_model_loaded: bool
