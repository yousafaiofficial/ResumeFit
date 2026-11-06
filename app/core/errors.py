import logging
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings

logger = logging.getLogger("resumefit.errors")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail if isinstance(exc.detail, str) else "An error occurred.",
            "details": exc.detail if not isinstance(exc.detail, str) else None,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    # Format message to be user-friendly
    first_error = errors[0] if errors else {}
    msg = first_error.get("msg", "Invalid input data provided.")
    loc = " -> ".join(str(l) for l in first_error.get("loc", []))
    if loc and loc != "body":
        msg = f"{loc}: {msg}"
        
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": msg,
            "details": errors,
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error processing %s: %s", request.url.path, exc)
    
    # In development mode, detail may be shown; in staging/prod, stack traces are never leaked
    detail = str(exc) if settings.APP_ENV == "dev" else None
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please try again later.",
            "details": detail,
        },
    )
