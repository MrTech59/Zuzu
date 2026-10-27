# Zuzu

**Zuzu** is an independent, self-contained agentic AI assistant (v0.1.0) with:

- A **FastAPI backend** (`apps/api`) with its own orchestrator, task state
  machine, memory system, policy engine, approvals, and audit log.
- A **Next.js frontend** (`apps/web`) for chat, tasks, approvals and memories.
- **NVIDIA cloud AI** integration (OpenAI-compatible endpoint) with a
  deterministic offline mock for development and tests.
- An **MCP client** (Streamable HTTP, verified live) for tool use with
  policy-gated permissions.
- **SQLite** for local development and **PostgreSQL** for Docker/production
  deployments, with Alembic migrations for both.

Zuzu is completely independent of OpenClaw, AstraAI and any other assistant —
see `docs/ARCHITECTURE.md#independence-statement` and the independence tests.

## System requirements

- **Python** 3.12 or newer (used by the backend and setup scripts).
- **Node.js** and **npm** (used to build and run the web frontend).
- One of:
  - **Windows** with PowerShell 5.1+,
  - **Linux** or **macOS**, or
  - **WSL2** on Windows.

Optional, depending on the path you choose:

- **Docker** and **Docker Compose** — only if you run the full
  PostgreSQL-backed stack via `scripts/setup.ps1` / `scripts/setup.sh`.
- **PostgreSQL** 16+ — only if you prefer a local Postgres database instead
  of SQLite for host development. The default host setup uses SQLite, so no
  external database is required.
- **NVIDIA API key** — only if you switch from the mock provider to live
  NVIDIA chat.

### Hardware requirements

Zuzu uses cloud AI providers, so no GPU is required locally.

| Setup | Min CPU cores | Rec. CPU cores | Min RAM | Rec. RAM | Min storage | Rec. storage |
|-------|---------------|----------------|---------|----------|-------------|--------------|
| Host dev (SQLite, no Docker) | 2 | 4 | 2 GB | 4 GB | 2 GB | 4 GB |
| Docker Compose stack (API + web + PostgreSQL) | 4 | 8 | 4 GB | 8 GB | 4 GB | 8 GB |

Notes:
- **CPU**: the Next.js frontend build and Docker image builds are the most
  CPU-intensive steps. Runtime usage is modest; 2 cores is enough for host
  development, and 4 cores handles the Docker stack comfortably.
- **RAM**: the Docker Compose stack runs three containers simultaneously
  (API, Next.js web UI, PostgreSQL). Docker Desktop on Windows/WSL adds its
  own memory overhead; 8 GB is much more comfortable.
- **Storage**: most space is consumed by Docker images, `node_modules`, and
  Python packages. The actual application data (SQLite/Postgres) starts at
  only a few megabytes.
- These numbers assume you are **not** running a local LLM. If you add local
  inference later, GPU, CPU, and RAM requirements are determined by that model.

## Quick start

Run the unified install script and choose **host** (SQLite + mock AI, no
Docker) or **Docker Compose** (PostgreSQL + NVIDIA live-chat ready):

```powershell
# Windows (run as Administrator to let the script install Python/Node)
scripts\install.ps1
```

```bash
# Linux / macOS / WSL (run as root on Debian/Ubuntu to install Python/Node)
bash scripts/install.sh
```

The script will ask which path you want. It can also install Python 3.12 and
Node.js for you when it is run with the necessary privileges. Non-interactive
usage:

```powershell
scripts\install.ps1 -UseHost        # or -UseDocker
scripts\install.ps1 -Update -UseHost # pull latest and reinstall
bash scripts/install.sh --host       # or --docker
bash scripts/install.sh --update --host # pull latest and reinstall
```

Then start the web dev server in a second terminal:

```powershell
cd apps\web
npm run dev                     # reachable on all interfaces, e.g. http://<ip>:3000
```

The host setup scripts automatically detect your machine's IP and write it
into `.env` as `NEXT_PUBLIC_ZUZU_API_URL` and `ZUZU_CORS_ORIGINS`, so the web
UI works from another device on the same network. The API and web dev servers
both bind to `0.0.0.0` by default.

The first-run wizard at `/setup` lets you confirm the API URL. In dev mode,
authentication is optional unless `ZUZU_API_KEY` is set in `.env`.

## Manual paths

If you prefer to run the underlying scripts directly:

```powershell
# Host development (SQLite + mock provider)
scripts\dev-setup.ps1
scripts\dev.ps1                  # binds API to 0.0.0.0:8000

# Docker Compose (PostgreSQL + NVIDIA live-chat ready)
scripts\setup.ps1
```

## Run as systemd services (Linux)

To keep the API and web UI running persistently on a Linux host, install and
start the provided systemd units:

```bash
bash scripts/install-services.sh   # requires root/sudo
```

This builds the web production bundle, installs `zuzu-api.service` and
`zuzu-web.service`, enables them, and starts them. The API binds to
`0.0.0.0:8000` and the web UI to `0.0.0.0:3000`, so both are reachable by IP
from the local network.

Use `systemctl status zuzu-api` / `systemctl status zuzu-web` and
`journalctl -u zuzu-api -f` / `journalctl -u zuzu-web -f` to manage them.

To update to the latest code and restart the services:

```bash
bash scripts/install-services.sh --update
```

`compose.yaml` loads environment variables directly from `.env` so secrets
are not subject to Docker Compose interpolation. The setup scripts rewrite
`DATABASE_URL` to point at the Docker Postgres service and set
`AI_PROVIDER=nvidia`. For Tailscale-only deployments, set `ZUZU_CORS_ORIGINS`
in `.env` to include the Tailscale origin before running `docker compose up`.

## Switching from mock to live NVIDIA chat

Edit `.env` after the host setup:

```dotenv
AI_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

Restart the API (`scripts\dev.ps1` / `scripts/dev.sh`). v0.1.0 was verified
live with `nvidia/nemotron-3.5-lightning-30b-a3b`. The earlier default
`meta/llama-3.3-70b-instruct` is end-of-life (HTTP 410).

If the API key can list models (`GET /v1/models` returns 200) but inference
returns HTTP 403, the key is missing the **Public API Endpoints** entitlement;
contact NVIDIA support to enable it.

## Tests & checks

```powershell
python -m pytest tests -q       # backend (offline, mock provider)
python -m ruff check apps/api/src tests migrations
python -m mypy apps/api/src
cd apps\web; npm test           # frontend unit tests
cd apps\web; npm run build      # frontend build
```

## MCP integration

Verified against the live browser MCP server (Streamable HTTP). Enable with:

```dotenv
ZUZU_MCP_ENABLED=true
ZUZU_MCP_SERVER_URL=http://192.168.3.137:8000/mcp
ZUZU_MCP_TRANSPORT=streamable-http
```

Verify anytime: `python scripts/verify_mcp.py --call browser_current`.
Details: `docs/MCP-INTEGRATION.md`.

## Documentation

- `docs/ARCHITECTURE.md` — components and independence statement
- `docs/SECURITY.md` — threat model and controls
- `docs/DATABASE.md` — schema, boundaries, vector-search deferral
- `docs/MCP-INTEGRATION.md` — verified transport and tool catalogue
- `docs/DEPLOYMENT.md` — Proxmox + Tailscale-only deployment
- `docs/IMPLEMENTATION_NOTES.md` — stage log, evidence, blockers

## License

MIT — see `LICENSE`.
