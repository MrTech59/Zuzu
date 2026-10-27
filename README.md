# Zuzu

**Zuzu** is an independent, self-contained agentic AI assistant (v0.1.0) with:

- A **FastAPI backend** (`apps/api`) with its own orchestrator, task state
  machine, memory system, policy engine, approvals, and audit log.
- A **Next.js frontend** (`apps/web`) for chat, tasks, approvals and memories.
- **NVIDIA cloud AI** integration (OpenAI-compatible endpoint) with a
  deterministic offline mock for development and tests.
- An **MCP client** (Streamable HTTP, verified live) for tool use with
  policy-gated permissions.
- **PostgreSQL** persistence with Alembic migrations.

Zuzu is completely independent of OpenClaw, AstraAI and any other assistant —
see `docs/ARCHITECTURE.md#independence-statement` and the independence tests.

## Quick start (offline, no credentials)

```powershell
python -m pip install -e ".[dev]"
copy .env.example .env          # defaults: mock provider, SQLite, MCP off
scripts\dev.ps1                 # migrations + API on http://127.0.0.1:8000
```

Frontend:

```powershell
cd apps\web
npm install
npm run dev                     # http://localhost:3000
```

Set the API key in the web header (any value in dev mode without a key; when
`ZUZU_API_KEY` is set, use that).

## Full stack with Docker

```powershell
# One-time setup: creates .env with generated secrets and starts the stack.
scripts\setup.ps1

# Or manually:
copy .env.example .env          # set ZUZU_API_KEY, POSTGRES_PASSWORD
docker compose up -d --build
```

On first visit, the web UI shows a link to `/setup` where you can enter the
API URL and key. For Tailscale-only deployments, set `ZUZU_CORS_ORIGINS` in
`.env` to include the Tailscale origin before running `docker compose up`.

## Tests & checks

```powershell
python -m pytest tests -q       # backend (offline, mock provider)
python -m ruff check apps/api/src tests migrations
python -m mypy apps/api/src
cd apps\web; npm test           # frontend unit tests
cd apps\web; npm run build      # frontend build
```

## Live NVIDIA chat

Set `NVIDIA_API_KEY` (and optionally `NVIDIA_MODEL`) in `.env` with
`AI_PROVIDER=nvidia`, restart, and chat.

```dotenv
AI_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

`NVIDIA_MODEL` overrides the default (`meta/llama-3.3-70b-instruct`). If the
API key returns HTTP 403 on `POST /v1/chat/completions` while
`GET /v1/models` succeeds, the key is missing the **Public API Endpoints**
entitlement; contact NVIDIA support to enable it.

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
