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

## Quick start (host, no Docker)

The fastest way to run locally. Uses SQLite and the mock AI provider, so no
external database or API key is required.

```powershell
# Windows
scripts\dev-setup.ps1          # installs deps, creates .env
scripts\dev.ps1                 # migrations + API on http://127.0.0.1:8000
```

```bash
# Linux / macOS / WSL
bash scripts/dev-setup.sh
bash scripts/dev.sh
```

Frontend (in a second terminal):

```powershell
cd apps\web
npm install
npm run dev                     # http://localhost:3000
```

The first-run wizard at `/setup` lets you confirm the API URL. In dev mode,
authentication is optional unless `ZUZU_API_KEY` is set in `.env`.

## Full stack with Docker (production-like)

```powershell
# Windows
scripts\setup.ps1               # creates .env, builds images, starts stack

# Linux / macOS / WSL
bash scripts/setup.sh
```

Or manually:

```powershell
copy .env.example .env          # set ZUZU_API_KEY, POSTGRES_PASSWORD, NVIDIA_API_KEY
docker compose up -d --build
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
