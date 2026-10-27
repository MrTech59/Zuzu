#!/usr/bin/env bash
# Unified Zuzu install script.
# Asks whether to install the Docker Compose stack (PostgreSQL + NVIDIA
# live-chat ready) or the host development environment (SQLite + mock
# provider, no Docker required), then runs the appropriate setup script.
#
# Non-interactive usage:
#   bash scripts/install.sh --docker
#   bash scripts/install.sh --host
#   bash scripts/install.sh --docker --skip-build
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

USE_DOCKER=false
USE_HOST=false
SKIP_BUILD=false

for arg in "$@"; do
    case "$arg" in
        --docker) USE_DOCKER=true ;;
        --host) USE_HOST=true ;;
        --skip-build) SKIP_BUILD=true ;;
    esac
done

if [[ "$USE_DOCKER" == false && "$USE_HOST" == false ]]; then
    echo ""
    echo "How would you like to run Zuzu?"
    echo ""
    echo "  [H] Host development (SQLite + mock AI provider, no Docker)"
    echo "  [D] Docker Compose (PostgreSQL + NVIDIA live-chat ready)"
    echo ""
    read -rp "Enter H or D (default H): " choice
    case "${choice^^}" in
        D) USE_DOCKER=true ;;
        *) USE_HOST=true ;;
    esac
fi

if [[ "$USE_DOCKER" == true ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: Docker is required for the Docker Compose path." >&2
        echo "Install Docker Desktop from https://www.docker.com/products/docker-desktop/" >&2
        exit 1
    fi
    args=()
    [[ "$SKIP_BUILD" == true ]] && args+=("--skip-build")
    echo "Running Docker Compose setup..."
    bash "$PROJECT_ROOT/scripts/setup.sh" "${args[@]}"
else
    if [[ "$SKIP_BUILD" == true ]]; then
        echo "WARNING: --skip-build is only used by the Docker path; ignoring." >&2
    fi
    echo "Running host development setup..."
    bash "$PROJECT_ROOT/scripts/dev-setup.sh"
fi
