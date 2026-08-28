"""FastAPI application: REST API for patient registration.

The voice / LLM layer will call the same service functions in app.services.patients
(or these HTTP endpoints) once telephony is wired up.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import LOG_LEVEL
from app.database import SessionLocal, engine, get_db
from app.exceptions import APIError
from app.models import Base
from app.routers.patients import router as patients_router
from app.seed import seed_if_empty

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("carecloud")


def _error_body(message: str, details: list[dict] | None = None) -> dict:
    return {"data": None, "error": {"message": message, "details": details}}


def _format_validation_details(errors: list[dict]) -> list[dict]:
    details = []
    for err in errors:
        loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path", "header")]
        field = ".".join(loc) if loc else "request"
        message = err.get("msg", "Invalid value")
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        details.append({"field": field, "message": message})
    return details


def create_app(*, initialize_db: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if initialize_db:
            Base.metadata.create_all(bind=engine)
            with SessionLocal() as db:
                seed_if_empty(db)
        yield

    application = FastAPI(
        title="CareCloud Patient Registration API",
        description=(
            "Persistent patient demographic store and REST API. "
            "The voice agent will persist confirmed registrations through this service."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    application.include_router(patients_router)

    @application.get("/health", tags=["meta"])
    def health():
        return {"data": {"status": "ok"}, "error": None}

    @application.get("/", include_in_schema=False)
    def root():
        return {
            "data": {
                "service": "CareCloud Patient Registration API",
                "docs": "/docs",
                "health": "/health",
            },
            "error": None,
        }

    @application.exception_handler(APIError)
    async def api_error_handler(_request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.message, exc.details),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, exc: RequestValidationError):
        errors = exc.errors()
        if any(item.get("type") == "json_invalid" for item in errors):
            return JSONResponse(
                status_code=400,
                content=_error_body("Invalid JSON in request body"),
            )
        return JSONResponse(
            status_code=422,
            content=_error_body("Request validation failed", _format_validation_details(errors)),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(status_code=exc.status_code, content=_error_body(message))

    @application.exception_handler(Exception)
    async def unhandled_error_handler(_request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body("An unexpected error occurred"),
        )

    return application


app = create_app()


# Re-export for tests that override the DB dependency.
__all__ = ["app", "create_app", "get_db"]
