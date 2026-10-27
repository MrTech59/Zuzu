#!/usr/bin/env bash
# Zuzu development startup (Linux/macOS/WSL).
# Starts the API with the mock provider and SQLite by default.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

HOST="0.0.0.0"
for arg in "$@"; do
    case "$arg" in
        --host=*)
            HOST="${arg#*=}"
            ;;
    esac
done

# Determine a friendly IP to show (first non-loopback IPv4 address).
DEV_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
DEV_IP="${DEV_IP:-$HOST}"

echo "== Zuzu dev: applying migrations =="
python -m alembic upgrade head

echo "== Zuzu dev: starting API on ${HOST}:8000 (reachable at http://${DEV_IP}:8000) =="
python -m uvicorn zuzu.main:app --host "$HOST" --port 8000 --reload
