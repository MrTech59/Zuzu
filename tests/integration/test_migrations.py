"""Migration tests: alembic upgrade from a clean database."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys


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


def test_upgrade_head_on_clean_database(tmp_path: pathlib.Path) -> None:
    db_file = tmp_path / "migration-test.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    assert db_file.exists()


def test_upgrade_then_downgrade_roundtrip(tmp_path: pathlib.Path) -> None:
    db_file = tmp_path / "migration-roundtrip.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    down = run_alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stdout + down.stderr
    up2 = run_alembic(url, "upgrade", "head")
    assert up2.returncode == 0, up2.stdout + up2.stderr
