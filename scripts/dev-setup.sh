#!/usr/bin/env bash
# One-time Zuzu host development setup for Linux/macOS/WSL.
# Installs Python and Node dependencies, creates .env from .env.example
# with generated secrets, and prints the commands needed to start the
# API and web dev servers.
#
# This uses SQLite and the mock AI provider by default, so no Docker or
# external database is required. For Docker Compose deployment, use
# scripts/setup.sh.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        echo "ERROR: python3 or python is required." >&2
        exit 1
    fi
fi

if ! "$PYTHON" -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "ERROR: Python 3.12 or newer is required." >&2
    exit 1
fi

for cmd in node npm; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: $cmd is required. Install Node.js from https://nodejs.org/" >&2
        exit 1
    fi
done

ENV_FILE="$PROJECT_ROOT/.env"
EXAMPLE_FILE="$PROJECT_ROOT/.env.example"

if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "ERROR: .env.example not found." >&2
    exit 1
fi

FORCE=false
GENERATE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
    esac
done

if [[ -f "$ENV_FILE" ]]; then
    if [[ "$FORCE" == true ]]; then
        echo ".env exists but --force supplied; regenerating secrets."
        GENERATE=true
    else
        echo ".env already exists; preserving existing secrets."
    fi
else
    GENERATE=true
fi

if [[ "$GENERATE" == true ]]; then
    API_KEY=$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')
    sed \
        -e "s/^ZUZU_API_KEY=.*/ZUZU_API_KEY=${API_KEY}/" \
        "$EXAMPLE_FILE" > "$ENV_FILE"
    echo ".env created with generated secrets (SQLite + mock provider by default)."
fi

# Ensure LF line endings (safe even if the file was edited with CRLF).
sed -i.bak -e 's/\r$//' "$ENV_FILE" && rm -f "$ENV_FILE.bak"

# Ensure a single trailing newline.
printf '\n' >> "$ENV_FILE"

if grep -q '@db:5432' "$ENV_FILE" 2>/dev/null; then
    echo "WARNING: DATABASE_URL still points to the Docker hostname (@db:5432)." >&2
    echo "Host dev will not start until you update it or re-run with --force." >&2
fi

echo 'Installing Python dependencies...'
"$PYTHON" -m pip install -e ".[dev]"

echo 'Installing Node dependencies...'
(cd "$PROJECT_ROOT/apps/web" && npm install)

cat <<'EOF'

Setup complete. Next steps:

1. Start the API dev server:
     scripts/dev.sh

2. In another terminal, start the web dev server:
     cd apps/web
     npm run dev

Web UI: http://localhost:3000
API:    http://127.0.0.1:8000/api/v1/health

To use live NVIDIA chat instead of the mock provider, set AI_PROVIDER=nvidia
and NVIDIA_API_KEY in .env, then restart the API. For a full Docker Compose
stack with PostgreSQL, run scripts/setup.sh.
EOF
