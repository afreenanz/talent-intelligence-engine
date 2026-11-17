"""Liveness vs readiness.

- live: the process is up. An orchestrator restarts the container if this fails.
- ready: dependencies are reachable. The orchestrator stops routing traffic if this fails,
  but doesn't restart (restarting won't fix a database outage).
"""

from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DbSession
from app.db.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])
log = structlog.get_logger(__name__)


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(session: DbSession) -> JSONResponse:
    checks: dict[str, Any] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("readiness_database_failed", error=str(exc))
        checks["database"] = "unavailable"
    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        log.warning("readiness_redis_failed", error=str(exc))
        checks["redis"] = "unavailable"
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
