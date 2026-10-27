"""Acceptance tests for one-time setup scripts.

These tests exercise the PowerShell and Bash setup scripts in isolated
temporary directories. They verify:
- Fresh installation creates .env with generated secrets.
- Re-running without --force is idempotent and preserves secrets.
- --force regenerates secrets.
- Secrets are never printed to stdout/stderr.
- .env line endings are normalized to LF.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_POWERSHELL = shutil.which("powershell")
_BASH = shutil.which("bash")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_fake_project(tmp_path: Path) -> Path:
    """Copy the minimal files a setup script needs into a temp directory."""
    project = tmp_path / "zuzu"
    project.mkdir()
    shutil.copy(REPO_ROOT / ".env.example", project / ".env.example")
    shutil.copytree(REPO_ROOT / "scripts", project / "scripts")
    shutil.copytree(REPO_ROOT / "apps", project / "apps")
    shutil.copy(REPO_ROOT / "compose.yaml", project / "compose.yaml")
    return project


def _read_env(project: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (project / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value
    return env


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script requires Windows")
def test_setup_ps1_fresh_installation(tmp_path: Path) -> None:
    project = _create_fake_project(tmp_path)
    script = project / "scripts" / "setup.ps1"
    result = subprocess.run(
        [_POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(script), "-SkipBuild"],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output

    env = _read_env(project)
    assert len(env["ZUZU_API_KEY"]) >= 32
    assert len(env["POSTGRES_PASSWORD"]) >= 16
    # Secrets must not be echoed.
    assert env["ZUZU_API_KEY"] not in output
    assert env["POSTGRES_PASSWORD"] not in output
    # LF line endings.
    assert "\r\n" not in (project / ".env").read_bytes().decode("utf-8", errors="replace")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script requires Windows")
def test_setup_ps1_idempotent_and_force(tmp_path: Path) -> None:
    project = _create_fake_project(tmp_path)
    script = project / "scripts" / "setup.ps1"
    # First run.
    subprocess.run(
        [_POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(script), "-SkipBuild"],
        cwd=str(project),
        capture_output=True,
        text=True,
        check=True,
    )
    first_key = _read_env(project)["ZUZU_API_KEY"]

    # Second run without -Force must keep the same key.
    subprocess.run(
        [_POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(script), "-SkipBuild"],
        cwd=str(project),
        capture_output=True,
        text=True,
        check=True,
    )
    assert _read_env(project)["ZUZU_API_KEY"] == first_key

    # Force regenerates.
    subprocess.run(
        [_POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(script), "-Force", "-SkipBuild"],
        cwd=str(project),
        capture_output=True,
        text=True,
        check=True,
    )
    assert _read_env(project)["ZUZU_API_KEY"] != first_key


@pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="Bash script requires a Unix-like shell",
)
def test_setup_sh_fresh_installation(tmp_path: Path) -> None:
    project = _create_fake_project(tmp_path)
    script = project / "scripts" / "setup.sh"
    result = subprocess.run(
        [_BASH, str(script), "--skip-build"],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output

    env = _read_env(project)
    assert len(env["ZUZU_API_KEY"]) >= 32
    assert len(env["POSTGRES_PASSWORD"]) >= 16
    assert env["ZUZU_API_KEY"] not in output
    assert env["POSTGRES_PASSWORD"] not in output
    assert "\r\n" not in (project / ".env").read_bytes().decode("utf-8", errors="replace")
