# Zuzu development startup (Windows).
# Starts the API with the mock provider and SQLite by default.

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== Zuzu dev: applying migrations =="
python -m alembic upgrade head

Write-Host "== Zuzu dev: starting API on 127.0.0.1:8000 =="
python -m uvicorn zuzu.main:app --host 127.0.0.1 --port 8000 --loop zuzu.db.engine:selector_loop_factory
