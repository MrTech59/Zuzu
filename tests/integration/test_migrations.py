"""Migration tests: alembic upgrade from a clean database.

By default the tests use a temporary SQLite file. Set
ZUZU_MIGRATION_DATABASE_URL to run them against PostgreSQL instead.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def default_db_url() -> str:
    """Return a test database URL, preferring the environment override."""
    env_url = os.environ.get("ZUZU_MIGRATION_DATABASE_URL")
    if env_url:
        return env_url
    # Fallback to a fresh SQLite file in the system temp directory.
    import tempfile

    return f"sqlite+aiosqlite:///{tempfile.mkstemp(suffix='.db')[1]}"


def run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ZUZU_MIGRATION_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(pathlib.Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_upgrade_head_on_clean_database() -> None:
    url = default_db_url()
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr


def test_upgrade_then_downgrade_roundtrip() -> None:
    url = default_db_url()
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    down = run_alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stdout + down.stderr
    up2 = run_alembic(url, "upgrade", "head")
    assert up2.returncode == 0, up2.stdout + up2.stderr
