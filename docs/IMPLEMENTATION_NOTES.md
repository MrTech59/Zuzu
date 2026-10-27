# Implementation Notes

Live record of completed work, verification evidence, assumptions, blockers
and unverified facts. Updated at each stage.

## Continuation — approved MCP tool verification (2026-10-27)

- Fixed an existing lint issue: removed unused `fingerprint` import from
  `apps/api/src/zuzu/orchestrator/runner.py` and a long line in
  `scripts/verify_mcp.py`.
- Added `scripts/verify_mcp_approved.py` to exercise Zuzu's own MCP client
  through the full approval gate against the live server.
- Verified:
  - Handshake to `http://192.168.3.137:8000/mcp` succeeds.
  - 22 tools discovered with actual JSON schemas.
  - `browser_navigate` input schema validated (`{url: string}`).
  - Zuzu's policy engine returns `approval_required` for the state-changing
    tool.
  - After explicit approval (`--yes`), the tool is invoked directly by
    `McpClient.invoke` and the browser state changes to the target URL.
  - Post-invocation `browser_current` confirms the navigation.
- Evidence captured in `docs/mcp-approved-evidence.json`.
- The MCP server was not modified; only a harmless navigation to
  `example.com` was performed.

## Environment inspection (2026-10-27)

- Workspace `G:\Dev\ZUZU` was **empty**; git repo freshly initialized. No
  pre-existing work to preserve.
- Tooling verified: Python 3.12.10, Node 24.14.1, npm 11.11.0, Docker
  29.6.1 + Compose v5.1.4, Git 2.55.0.
- Docker daemon was not running at inspection time; Docker Desktop was
  launched during the session (status checked before compose use).
- NVIDIA API contract verified from public documentation only (OpenAI-style
  `/chat/completions`, Bearer auth, base `https://integrate.api.nvidia.com/v1`).
  **No NVIDIA_API_KEY available in this environment, so live NVIDIA
  requests are unverified.** The adapter is implemented and mock-tested;
  live verification is pending credentials.

## MCP verification (LIVE, evidence in docs/mcp-live-evidence.json)

- TCP to `192.168.3.137:8000` reachable from this machine.
- Historical "session-based SSE" report is **incorrect**: all of `/`, `/sse`,
  `/docs`, `/openapi.json`, `/health` return 404.
- Real transport: **Streamable HTTP at `/mcp`** (verified with a full
  initialize handshake; `mcp-session-id` header; `notifications/initialized`
  → 202; negotiated protocol `2025-11-25`).
- Server: `picoclaw-browser` v1.30.0.
- 22 tools discovered with schemas; `browser_navigate` verified with input
  schema `{url: string (required)}`.
- Live read-only tool call (`browser_current`) succeeded and returned real
  browser state.
- The MCP server was NOT modified in any way.

## Assumptions

- Single-user v0.1.0: one default user row (`users.username = 'local'`);
  auth via a single `ZUZU_API_KEY` bearer token. Multi-user auth deferred.
- Postgres runs in Docker Compose for deployment; SQLite is a documented
  dev/test convenience (the DB layer stays dialect-portable).
- Tasks execute in-process (asyncio) for v0.1.0 — acceptable under the
  current read-only-with-approval permission scope; isolated worker is the
  documented next step.

## Stage completion log

### Stage 1 — Foundation (complete)
- Config (pydantic-settings), redacting logging, error envelope, FastAPI app
  factory, public `/api/v1/health`, protected `/api/v1/ready`, bearer-token
  auth dependency, startup guard refusing keyless production runs.
- Tests: health safety, auth enforcement, production guard, independence.

### Stage 2 — Database (complete)
- SQLAlchemy 2.x models (users, conversations, messages, memories, tasks,
  task_steps, approvals, audit_events), async engine, Alembic migration
  `0001_initial`, memory service with keyword retrieval.
- Tests: model round-trips/cascades, clean-DB migration, upgrade/downgrade
  round-trip, memory search/delete. Migration tests run against SQLite via
  ZUZU_MIGRATION_DATABASE_URL; Postgres path is exercised in compose.

### Stage 3 — NVIDIA chat (complete)
- Provider abstraction (`ai/base.py`), NVIDIA adapter (timeouts, bounded
  retries, SSE streaming, clear error mapping, no key in logs/errors),
  deterministic mock provider, chat endpoints (JSON + SSE), conversation
  listing/detail.
- Tests: success, auth error, rate-limit retry, server error, invalid shape,
  SSE chunking, streaming endpoint, history persistence, error-stream event.
- **Live NVIDIA chat: unverified (no API key in this environment).**

### Stage 4 — Orchestration (complete)
- Task state machine with validated transitions and success guard; TaskRunner
  (planning → running → awaiting_approval → resume → succeeded/failed);
  bounded steps/deadline; cancellation; honest failure reasons.
- Policy engine (default-deny, YAML rules, agent profiles), approval service
  (fingerprint binding, single-use `used` status, expiry, changed-action
  rejection), audit logging with redaction.
- Tests: policy matrix, state machine, approvals semantics, task lifecycle,
  cancellation, prompt-injection guard, redaction.

### Stage 5 — MCP client (complete, LIVE-VERIFIED)
- Zuzu's own MCP client (official SDK, Streamable HTTP) + registry + mock;
  schema validation; bounded timeouts/retries; graceful unavailability.
- Live verification performed (handshake + discovery + read-only call);
  evidence committed.

### Stage 6 — Frontend (complete)
- Next.js (App Router) + TypeScript in `apps/web`: chat with streaming,
  conversation history, task list/detail/cancel, approvals with decisions,
  memory list/delete, health status indicator, responsive layout, loading and
  error states. Vitest unit tests for the API client. Playwright config
  provided for e2e (runs when the stack is up).

### Stage 7 — Release prep (complete)
- Formatting, linting, typecheck, full test suite — see report in the final
  session summary; README with run instructions; release checklist below.

## Blockers / unverified items

1. **NVIDIA live chat** — needs `NVIDIA_API_KEY`. Everything else works
   offline via the mock provider.
2. **Postgres-backed integration run** — the migration suite runs on SQLite;
   the Postgres path is wired in compose and exercised manually when Docker
   is available. Docker Desktop was started during this session; run
   `docker compose up -d db && alembic upgrade head` with a real
   `DATABASE_URL` to confirm on Postgres.
3. **Frontend e2e (Playwright)** — config provided; browsers not installed
   during this session (`npx playwright install` needed).

## Independence verification

- `test_independence_core_works_without_external_agents` — chat, tasks and
  memories all work with MCP disabled and the mock provider (i.e. no external
  agents running).
- `test_no_external_agent_references_in_source` — no source references to
  OpenClaw/AstraAI.
- Zuzu has its own DB schema and owns all its state.
