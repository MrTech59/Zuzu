"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zuzu import __version__
from zuzu.api.deps import require_auth
from zuzu.config import get_settings
from zuzu.errors import install_error_handlers

logger = logging.getLogger("zuzu.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    from zuzu.logging import register_secret

    if settings.zuzu_api_key:
        register_secret(settings.zuzu_api_key)
    if settings.nvidia_api_key:
        register_secret(settings.nvidia_api_key)

    settings.assert_runnable()
    if not settings.auth_enforced:
        logger.warning(
            "AUTH IS DISABLED: running in development mode without ZUZU_API_KEY. "
            "Bind to localhost only."
        )

    # Database (optional at startup; readiness reports status).
    from zuzu.db.engine import init_engine, shutdown_engine

    init_engine()
    try:
        # MCP registry (optional; app must work when MCP is unreachable).
        if settings.mcp_enabled:
            from zuzu.integrations.mcp.registry import init_registry

            await init_registry()
    except Exception:
        logger.warning("MCP registry failed to initialize; continuing without MCP.", exc_info=True)

    try:
        yield
    finally:
        await shutdown_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Zuzu API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if not settings.is_dev else "/docs",
        redoc_url=None,
    )

    install_error_handlers(app)

    # CORS: allow the local web frontend. Credentials are not used; the API is
    # bearer-token based, so wildcard origins cannot steal credentials, but we
    # still keep the list explicit.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )

    # Route modules are imported lazily to keep startup resilient when optional
    # integrations are unavailable.
    from zuzu.api.routes.chat import router as chat_router
    from zuzu.api.routes.health import router as health_router
    from zuzu.api.routes.memories import router as memories_router
    from zuzu.api.routes.tasks import router as tasks_router

    # Health is public; everything else requires auth.
    app.include_router(health_router)
    auth_dependency = Depends(require_auth)
    for r in (chat_router, tasks_router, memories_router):
        app.include_router(r, dependencies=[auth_dependency])

    return app


app = create_app()
