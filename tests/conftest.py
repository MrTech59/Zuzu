"""Shared test fixtures.

Tests run fully offline: mock AI provider, SQLite (aiosqlite) database, mock
MCP registry. No external credentials are required.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

# --- Environment hardening for tests (set before importing zuzu) -------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("NVIDIA_API_KEY", "")
os.environ.setdefault("ZUZU_API_KEY", "test-key-12345")
os.environ.setdefault("ZUZU_MCP_ENABLED", "false")

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def sqlite_db(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    db_file = tmp_path / "zuzu-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    yield db_file
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture()
async def client(sqlite_db: pathlib.Path) -> AsyncIterator[httpx.AsyncClient]:
    """Test client wired to a fresh SQLite-backed app instance."""
    from zuzu.ai.factory import reset_provider
    from zuzu.config import reset_settings_cache
    from zuzu.db import engine as db_engine
    from zuzu.db.base import Base
    from zuzu.integrations.mcp import registry as mcp_registry
    from zuzu.main import create_app

    reset_settings_cache()
    reset_provider()
    await db_engine.shutdown_engine()
    mcp_registry.set_registry(None)

    app = create_app()
    # Create schema directly from models (migration path is tested separately).
    engine = db_engine.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    await db_engine.shutdown_engine()
    mcp_registry.set_registry(None)
    reset_settings_cache()
    reset_provider()


@pytest.fixture()
async def db_schema(sqlite_db: pathlib.Path) -> AsyncIterator[None]:
    """DB-only fixture: fresh engine + schema, no HTTP client."""
    from zuzu.ai.factory import reset_provider
    from zuzu.config import reset_settings_cache
    from zuzu.db import engine as db_engine
    from zuzu.db.base import Base
    from zuzu.integrations.mcp import registry as mcp_registry

    reset_settings_cache()
    reset_provider()
    await db_engine.shutdown_engine()
    mcp_registry.set_registry(None)

    engine = db_engine.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db_engine.shutdown_engine()
    mcp_registry.set_registry(None)
    reset_settings_cache()
    reset_provider()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    from zuzu.config import get_settings

    return {"Authorization": f"Bearer {get_settings().zuzu_api_key}"}
