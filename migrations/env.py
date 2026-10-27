"""Alembic environment for Zuzu migrations.

The database URL is taken from Zuzu settings (DATABASE_URL), falling back to
alembic.ini's sqlalchemy.url when running inside Docker with its own env.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from zuzu.config import Settings
from zuzu.db import models  # noqa: F401  (registers tables on Base.metadata)
from zuzu.db.base import Base

config = context.config


def _database_url() -> str:
    url = os.environ.get("ZUZU_MIGRATION_DATABASE_URL", "")
    if url:
        return url
    try:
        return Settings().database_url  # type: ignore[call-arg]
    except Exception:
        return config.get_main_option("sqlalchemy.url") or ""


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (SQL script emission)."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    url = _database_url()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _database_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import sys

    if sys.platform == "win32":
        from zuzu.db.engine import ensure_selector_loop

        ensure_selector_loop()
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
