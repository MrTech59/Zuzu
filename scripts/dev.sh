#!/usr/bin/env bash
# Zuzu development startup (Linux/macOS/WSL).
# Starts the API with the mock provider and SQLite by default.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "== Zuzu dev: applying migrations =="
python -m alembic upgrade head

echo "== Zuzu dev: starting API on 127.0.0.1:8000 =="
python -m uvicorn zuzu.main:app --host 127.0.0.1 --port 8000 --reload
