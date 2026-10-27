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

## v0.1.0 release prep verification (2026-10-27)

### PostgreSQL-backed integration
- Ran `docker compose exec api sh -c 'alembic downgrade base && alembic upgrade head'`
  against the Compose Postgres database: completed successfully.
- Created a memory via `POST /api/v1/memories`, restarted the `api` container,
  and confirmed the memory was still present via `GET /api/v1/memories`.
- `GET /api/v1/ready` (authenticated) returns `{"ready":true,"checks":{"database":"ok","mcp":"disabled"}}`.

### Playwright end-to-end tests
- Installed Chromium with `npx playwright install --with-deps chromium`.
- Ran `npx playwright test` against the running Compose stack.
- Result: **5 passed** (chat round trip, tasks page, approvals page,
  memories create/delete, first-run setup wizard).
- Fixed `playwright.config.ts` to trim `ZUZU_API_KEY` so CRLF in `.env`
  cannot produce an invalid Authorization header.

### NVIDIA live-chat smoke test
- The host environment has `NVIDIA_API_KEY` set, so the provider was not
  blocked by a missing key.
- `GET https://integrate.api.nvidia.com/v1/models` with the configured key
  returns HTTP 200 and lists models, confirming the key is valid.
- `POST /v1/chat/completions` with the candidate model
  `nvidia/nemotron-3.5-lightning-30b-a3b` returns **HTTP 403 Forbidden**.
- This is consistent with NVIDIA's documented behavior: the API key lacks the
  **Public API Endpoints** entitlement. `GET /v1/models` succeeds while
  inference requests fail with 403 until NVIDIA support enables the scope.
- Previous default model `meta/llama-3.3-70b-instruct` returns **HTTP 410 Gone**
  (EOL 2026-08-26).
- **Status: blocked by provider-side account entitlement, not by code or
  model identifier.** The model ID is correct per the NVIDIA catalog and API
  reference docs. A key with the Public API Endpoints scope is required to
  complete live verification.

### Linux setup workflow verification
- Ran `scripts/setup.sh --skip-build` inside WSL2 (Ubuntu) from a clean copy
  of the repository.
- Result: script executed successfully, generated `.env`, populated
  `ZUZU_API_KEY` and `POSTGRES_PASSWORD`, and produced LF line endings.
- The CI workflow also runs the same script path on `ubuntu-latest`, so both
  local WSL and GitHub Actions Linux paths are covered.

### Security review
- Auth dependency uses constant-time `hmac.compare_digest`; only
  `/api/v1/health` is public.
- CORS origins were hardcoded to `localhost:3000`; made them configurable
  via `ZUZU_CORS_ORIGINS` (`apps/api/src/zuzu/config.py` and `main.py`).
- Added regression tests for default CORS origins and configurable origins.
- Approval binding, expiry, single-use consumption, and changed-action
  rejection were already covered by existing tests.
- Audit redaction tests already verify sensitive keys and bearer-like
  strings are redacted.
- Containers run as non-root `zuzu` user; no Docker socket or host DB port
  is exposed.

### Backup / restore
- Created a backup with `docker compose exec db pg_dump -U zuzu -d zuzu -Fc -f /tmp/zuzu-test.dump`
  (17.2 KB).
- Restored into a new `restoretest` database with `pg_restore` and verified
  `memories` row count = 1. Dump format and restore procedure work.

### Backend quality suites
- `python -m ruff check apps/api/src tests migrations scripts` — passed.
- `python -m ruff format --check apps/api/src tests migrations scripts` — passed.
- `python -m mypy apps/api/src` — passed.
- `python -m pytest tests -q` — passed (one skipped bash-only test on Windows).

### Standalone architecture requirements
- Added `scripts/setup.ps1` and `scripts/setup.sh`: idempotent, generate
  `ZUZU_API_KEY` and `POSTGRES_PASSWORD` from `.env.example`, normalize
  `.env` to LF, and build/start the Docker Compose stack. `-Force` /
  `--force` regenerates secrets; `-SkipBuild` / `--skip-build` skips Docker.
- Added `tests/acceptance/test_setup_scripts.py`: verifies fresh install,
  idempotency, `--force` regeneration, and that secrets are not echoed.
- Added browser-based first-run setup wizard at `/setup`: collects API base
  URL and key, validates health/ready, stores values in `localStorage`, and
  redirects to the chat page. The chat page links to the wizard when no key
  is stored. The wizard shows an "already configured" state when a key
  exists (wizard takeover protection).
- Added `.github/workflows/ci.yml` for cross-platform lint/type/test on
  Ubuntu and Windows, plus a Docker Compose smoke test on Ubuntu.

## Blockers / unverified items

1. **NVIDIA live chat** — blocked by the provider-side account entitlement
   **Public API Endpoints**. The configured key can list models (HTTP 200) but
   gets HTTP 403 on `POST /v1/chat/completions` for the correct model ID
   `nvidia/nemotron-3.5-lightning-30b-a3b`. The default model
   `meta/llama-3.3-70b-instruct` is EOL (HTTP 410). The code adapter is
   implemented and tested; live inference requires a key with the proper
   scope enabled by NVIDIA support.
2. **Live MCP verification** — MCP remains disabled in `.env`
   (`ZUZU_MCP_ENABLED=false`). Previous sessions verified the live MCP
   server; this session did not re-run live MCP tests.

## Release readiness

- Compose stack builds and starts cleanly on Windows.
- API health/ready pass; Postgres migrations and persistence verified.
- Playwright e2e suite passes against the running stack.
- Backend lint/format/type-check/test suites pass.
- Backup/restore verified against Postgres.
- Setup scripts, first-run wizard, and acceptance tests are implemented.
- Linux setup workflow verified in WSL2; CI covers Ubuntu and Windows.
- **Remaining before tagging v0.1.0**: the NVIDIA live-chat verification is
  blocked by the **Public API Endpoints** entitlement on the configured key.
  Once NVIDIA support enables that scope, rerun the live chat test and
  update this note. Otherwise the release is code-ready and fully verified
  offline.

## Independence verification

- `test_independence_core_works_without_external_agents` — chat, tasks and
  memories all work with MCP disabled and the mock provider (i.e. no external
  agents running).
- `test_no_external_agent_references_in_source` — no source references to
  OpenClaw/AstraAI.
- Zuzu has its own DB schema and owns all its state.
