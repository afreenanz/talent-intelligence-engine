"""Application factory: wires middleware, error handlers and routers. No business logic here."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.domains.auth.router import router as auth_router
from app.domains.candidates.router import router as candidates_router
from app.domains.interactions.router import router as interactions_router
from app.domains.jobs.router import router as jobs_router
from app.domains.preferences.router import router as preferences_router
from app.domains.resumes.router import router as resumes_router
from app.domains.search.router import router as search_router

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("http")

    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Reuse a caller-supplied request ID only if it is well-formed (avoids log injection).
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    register_exception_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth_router)
    v1.include_router(candidates_router)
    v1.include_router(search_router)
    v1.include_router(jobs_router)
    v1.include_router(resumes_router)
    v1.include_router(interactions_router)
    v1.include_router(preferences_router)
    app.include_router(health.router)
    app.include_router(v1)
    return app


app = create_app()
