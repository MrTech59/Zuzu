#!/usr/bin/env bash
# Unified Zuzu install script.
# Asks whether to install the Docker Compose stack (PostgreSQL + NVIDIA
# live-chat ready) or the host development environment (SQLite + mock
# provider, no Docker required), then runs the appropriate setup script.
#
# On Debian/Ubuntu and macOS, the host path can install Python 3.12 and
# Node.js automatically when run with root/admin privileges.
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

install_prereqs() {
    local missing=()

    if ! { command -v python3.12 >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; }; then
        missing+=("python")
    elif command -v python3.12 >/dev/null 2>&1; then
        : # ok
    elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
        : # ok
    elif command -v python >/dev/null 2>&1 && python -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
        : # ok
    else
        missing+=("python")
    fi

    if ! command -v node >/dev/null 2>&1; then
        missing+=("node")
    fi
    if ! command -v npm >/dev/null 2>&1; then
        missing+=("npm")
    fi

    if [[ ${#missing[@]} -eq 0 ]]; then
        return 0
    fi

    echo "Missing prerequisites: ${missing[*]}" >&2

    if [[ "$EUID" -ne 0 ]]; then
        echo "Re-run this script as root (or install Python 3.12 and Node.js yourself) to install them automatically." >&2
        echo "Manual install: sudo apt install python3.12 python3-pip nodejs npm  # Debian/Ubuntu" >&2
        exit 1
    fi

    if command -v apt-get >/dev/null 2>&1; then
        echo "Installing Python 3.12 and Node.js via apt..." >&2
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq python3.12 python3.12-venv python3-pip curl ca-certificates gnupg

        NODE_MAJOR=22
        mkdir -p /etc/apt/keyrings
        curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
        echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
        apt-get update -qq
        apt-get install -y -qq nodejs
    elif command -v brew >/dev/null 2>&1; then
        echo "Installing Python 3.12 and Node.js via Homebrew..." >&2
        brew install python@3.12 node
    else
        echo "Unsupported package manager. Install Python 3.12 and Node.js manually." >&2
        exit 1
    fi
}

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
    install_prereqs
    export PYTHON="${PYTHON:-python3.12}"
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        export PYTHON=python3
    fi
    echo "Running host development setup..."
    bash "$PROJECT_ROOT/scripts/dev-setup.sh"
fi
