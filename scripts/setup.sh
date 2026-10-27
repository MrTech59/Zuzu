#!/usr/bin/env bash
# One-time Zuzu setup for Linux/macOS/WSL.
# Creates .env from .env.example with generated secrets, builds the Docker
# Compose images, and starts the stack. Re-running is safe: existing .env
# secrets are preserved unless --force is used.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

for cmd in docker; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: $cmd is required." >&2
        exit 1
    fi
done

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        echo "ERROR: python3 or python is required." >&2
        exit 1
    fi
fi

ENV_FILE="$PROJECT_ROOT/.env"
EXAMPLE_FILE="$PROJECT_ROOT/.env.example"

if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "ERROR: .env.example not found." >&2
    exit 1
fi

FORCE=false
SKIP_BUILD=false
GENERATE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        --skip-build) SKIP_BUILD=true ;;
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
    PG_PASSWORD=$("$PYTHON" -c 'import secrets, string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))')
    sed \
        -e "s/^AI_PROVIDER=.*/AI_PROVIDER=nvidia/" \
        -e "s/^ZUZU_API_KEY=.*/ZUZU_API_KEY=${API_KEY}/" \
        -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${PG_PASSWORD}/" \
        -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://zuzu:${PG_PASSWORD}@db:5432/zuzu|" \
        "$EXAMPLE_FILE" > "$ENV_FILE"
fi

# Ensure LF line endings (safe even if the file was edited with CRLF).
sed -i.bak -e 's/\r$//' "$ENV_FILE" && rm -f "$ENV_FILE.bak"

# Ensure a single trailing newline.
printf '\n' >> "$ENV_FILE"

if grep -Eq '@127\.0\.0\.1:5432|sqlite' "$ENV_FILE" 2>/dev/null; then
    echo "WARNING: DATABASE_URL appears to point to a host database or SQLite." >&2
    echo "Run with --force to regenerate a Docker Compose .env, or update DATABASE_URL manually." >&2
fi

if [[ "$GENERATE" == true ]]; then
    echo ".env created with generated secrets (database host set to db)."
fi

if [[ "$SKIP_BUILD" == true ]]; then
    echo "Skipping Docker Compose build because --skip-build was specified."
else
    echo "Building Docker Compose images..."
    docker compose build

    echo "Starting Zuzu stack..."
    docker compose up -d

    echo "Zuzu is starting."
    echo "  Web UI:   http://127.0.0.1:3000"
    echo "  API:      http://127.0.0.1:8000/api/v1/health"
    echo "To inspect logs: docker compose logs -f"
fi
