"""Health and readiness endpoints.

- GET /api/v1/health  : liveness. Always safe, reveals no configuration.
- GET /api/v1/ready   : readiness. Reports DB connectivity and MCP availability
  without exposing credentials, hosts or other private infrastructure details.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from zuzu.api.deps import require_auth
from zuzu.config import Settings, get_settings

logger = logging.getLogger("zuzu.api.health")
router = APIRouter(prefix="/api/v1", tags=["health"])

_started_at = time.time()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    uptime_seconds: float


class ReadinessChecks(BaseModel):
    database: Literal["ok", "unavailable", "not_configured"]
    mcp: Literal["ok", "disabled", "unavailable"]


class ReadyResponse(BaseModel):
    ready: bool
    checks: ReadinessChecks


def _mcp_status(settings: Settings) -> str:
    """Report MCP availability. Never leaks the server URL or host."""
    if not settings.mcp_enabled:
        return "disabled"
    from zuzu.integrations.mcp.registry import get_registry

    registry = get_registry()
    if registry is None or not registry.healthy:
        return "unavailable"
    return "ok"


async def _db_status(settings: Settings) -> str:
    try:
        from sqlalchemy import text

        from zuzu.db.engine import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.warning("Database readiness check failed", exc_info=True)
        return "unavailable"


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    from zuzu import __version__

    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=round(time.time() - _started_at, 3),
    )


@router.get("/ready", response_model=ReadyResponse, dependencies=[Depends(require_auth)])
async def ready(settings: Settings = Depends(get_settings)) -> ReadyResponse:
    checks = ReadinessChecks(
        database=await _db_status(settings),  # type: ignore[arg-type]
        mcp=_mcp_status(settings),  # type: ignore[arg-type]
    )
    return ReadyResponse(
        ready=checks.database == "ok",
        checks=checks,
    )


def include_ready_probe_details() -> dict[str, Any]:
    """Reserved for future detail endpoints; intentionally empty."""
    return {}
