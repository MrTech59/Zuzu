#!/usr/bin/env bash
# Install or update Zuzu API and web UI as systemd services.
# Run as root (or with sudo).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

UPDATE=false
for arg in "$@"; do
    case "$arg" in
        --update) UPDATE=true ;;
        --help)
            echo "Usage: $0 [--update]"
            echo ""
            echo "  --update  Pull the latest code, rebuild, and restart the services."
            exit 0
            ;;
    esac
done

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (or with sudo)." >&2
    exit 1
fi

SERVICE_USER="${SUDO_USER:-${USER:-root}}"
PYTHON_BIN="$(command -v python3.12 || command -v python3 || command -v python)"
NPM_BIN="$(command -v npm)"

if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: Python not found." >&2
    exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "ERROR: Python 3.12 or newer is required." >&2
    exit 1
fi
if [[ -z "$NPM_BIN" ]]; then
    echo "ERROR: npm not found." >&2
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    echo "ERROR: $PROJECT_ROOT/.env not found. Run scripts/install.sh first." >&2
    exit 1
fi

install_units() {
    echo "Installing systemd units..."
    mkdir -p /etc/systemd/system
    for service in api web; do
        sed \
            -e "s|{{REPO_PATH}}|$PROJECT_ROOT|g" \
            -e "s|{{USER}}|$SERVICE_USER|g" \
            -e "s|{{PYTHON}}|$PYTHON_BIN|g" \
            -e "s|{{NPM}}|$NPM_BIN|g" \
            "$PROJECT_ROOT/scripts/services/zuzu-${service}.service.template" \
            > "/etc/systemd/system/zuzu-${service}.service"
    done
    systemctl daemon-reload
    systemctl enable zuzu-api.service zuzu-web.service
}

build_web() {
    echo "Installing Python dependencies..."
    "$PYTHON_BIN" -m pip install -e ".[dev]"

    echo "Building web production bundle..."
    (cd "$PROJECT_ROOT/apps/web" && "$NPM_BIN" install && "$NPM_BIN" run build)
}

start_services() {
    echo "Starting services..."
    systemctl start zuzu-api.service

    # Wait for API health before starting the web UI.
    for i in {1..30}; do
        if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    systemctl start zuzu-web.service
}

if [[ "$UPDATE" == true ]]; then
    echo "Updating Zuzu services..."
    systemctl stop zuzu-api.service zuzu-web.service || true

    echo "Pulling latest code..."
    git config --global --add safe.directory "$PROJECT_ROOT" 2>/dev/null || true
    git -C "$PROJECT_ROOT" pull origin main

    build_web
    install_units
    start_services

    echo ""
    echo "Update complete."
else
    build_web
    install_units
    start_services

    echo ""
    echo "Services installed and started."
fi

echo ""
systemctl status zuzu-api.service --no-pager
systemctl status zuzu-web.service --no-pager
