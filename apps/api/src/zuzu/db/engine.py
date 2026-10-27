"""Database engine and session management.

Postgres (postgresql+psycopg) is the production target. SQLite (aiosqlite) is
supported so unit tests and offline development run without external services.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("zuzu.db")


def ensure_selector_loop() -> None:
    """psycopg async mode requires a selector event loop; Windows defaults to
    Proactor. uvicorn sets this itself, but alembic/tests must too."""
    if sys.platform == "win32":
        policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_cls is not None and not isinstance(asyncio.get_event_loop_policy(), policy_cls):
            asyncio.set_event_loop_policy(policy_cls())


# Apply immediately on import: the policy must be set before asyncio.run()
# creates the loop, and every entry point imports this module eventually.
ensure_selector_loop()


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn --loop entry point.

    uvicorn >=0.36 hardcodes ProactorEventLoop on Windows, which psycopg
    async cannot use. Launch with:
        uvicorn zuzu.main:app --loop zuzu.db.engine:selector_loop_factory
    to force a SelectorEventLoop on any platform.
    """
    return asyncio.SelectorEventLoop()


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine(database_url: str) -> AsyncEngine:
    kwargs: dict[str, object] = {
        "echo": False,
        "future": True,
    }
    if database_url.startswith("sqlite"):
        kwargs["pool_pre_ping"] = False
    else:
        kwargs.update(
            {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
            }
        )
    return create_async_engine(database_url, **kwargs)  # type: ignore[arg-type]


def init_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the process-wide engine (idempotent)."""
    global _engine, _session_factory
    if _engine is None:
        ensure_selector_loop()
        from zuzu.config import get_settings

        url = database_url or get_settings().database_url
        _engine = _create_engine(url)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        logger.info("Database engine initialized (dialect=%s)", _engine.dialect.name)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


async def shutdown_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed")
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
