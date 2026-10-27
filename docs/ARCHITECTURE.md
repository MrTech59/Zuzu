# Zuzu Architecture

Zuzu is an independent, self-contained agentic AI assistant. It owns its own
orchestrator, task system, memory, database, AI provider integration, MCP
client, policy engine, API and frontend. **It is not a wrapper around, and
does not depend on, OpenClaw, AstraAI or any other assistant.**

## Independence statement

- The orchestrator, agent lifecycle, task queue/state machine, conversation
  system, memory, database, migrations, NVIDIA provider integration, MCP
  client/registry, permission engine, audit log, web frontend and backend API
  are all implemented inside this repository (`apps/api`, `apps/web`).
- No source code, databases, credentials, agent profiles, prompts or
  configuration are shared with OpenClaw, AstraAI or other existing projects.
- Zuzu continues to run chat, database, task management and memory when
  OpenClaw, AstraAI, other agents and the MCP server are offline — enforced by
  `tests/unit/test_health_and_independence.py::test_independence_core_works_without_external_agents`
  and `test_no_external_agent_references_in_source`.
- The existing browser MCP server (`picoclaw-browser` at `192.168.3.137:8000`)
  is a *tool service* Zuzu connects to as a client. Zuzu never delegates
  thinking or orchestration to it.

## Component map

```text
apps/web (Next.js + TS)          User interface: chat, tasks, approvals, memories
   │  HTTP (Bearer token)
   ▼
apps/api (FastAPI, src/zuzu/)    Backend API + application core
   ├── api/routes/               HTTP contract (health, chat, tasks, approvals, memories)
   ├── ai/                       Provider abstraction: NVIDIA adapter + deterministic mock
   ├── orchestrator/             Task state machine, runner, agent profiles, approvals
   ├── policy/                   Default-deny policy engine + system prompt builder
   ├── memory/                   Durable memory (keyword-retrieval, Postgres-backed)
   ├── audit/                    Append-only audit events with secret redaction
   ├── integrations/mcp/         Zuzu's MCP client (Streamable HTTP) + registry + mock
   └── db/                       SQLAlchemy 2.x models, async engine
migrations/ (Alembic)            Schema migrations (0001_initial: 8 tables)
policies/ (tools.yaml, agents.yaml)  Machine-enforceable permission rules
agents/ (*.md)                   Agent profile documentation / prompt material
```

## Request flows

### Chat
1. `POST /api/v1/chat` (auth) → validate limits → persist user message.
2. Build system prompt server-side; append recent history (bounded).
3. Provider (`NvidiaProvider` or `MockProvider`) completes or streams.
4. Persist assistant message; return JSON or SSE stream.
Failures surface as `502 provider_*` errors — never silent success.

### Task
1. `POST /api/v1/tasks` creates a `queued` task, starts the runner.
2. Runner: `planning` (AI produces a JSON plan; fallback single respond step),
   then `running` executes steps.
3. Each step is policy-checked:
   - `allow` → execute immediately (read-only browser tools, respond).
   - `approval_required` → persist approval bound to the exact action
     fingerprint; task → `awaiting_approval`; runner returns.
   - `deny` → step fails; task → `failed` with the policy reason.
4. Decision via `POST /api/v1/approvals/{id}/decision` → task resumes
   (`running`), consuming the approval single-use after re-checking the
   fingerprint.
5. Success requires all steps succeeded/skipped and zero pending approvals
   (`assert_can_succeed`). Failure and cancellation are explicit terminal
   states with recorded reasons.

### MCP tool call
`registry.invoke(tool, params)` — schema-validated against the discovered
input schema, bounded timeout/retries, audited (redacted). The policy engine
decides *whether* the call may happen at all.

## State machine

`queued → planning → running → awaiting_approval → running → succeeded`
plus terminal `failed` / `cancelled`. All transitions validated in
`orchestrator/state_machine.py`.

## Data boundaries

| Store | Content | Lifetime |
| --- | --- | --- |
| messages | conversation turns | history; deletable with the conversation |
| memories | durable user-approved facts | deletable individually by the user |
| tasks/steps | orchestration records + results | task lifetime |
| approvals | exact-action checkpoints | TTL + single-use |
| audit_events | security-relevant events | append-only (redacted) |

Secrets are never stored in any of them; the audit service redacts before
write, and the logging layer redacts at emission.

## Technology choices

- **Python 3.12 + FastAPI + SQLAlchemy 2.x (async) + Alembic + PostgreSQL**
  (psycopg 3). SQLite (aiosqlite) is supported as a dev/test convenience.
- **httpx** for the NVIDIA adapter (SSE streaming, timeouts, retries).
- **Official `mcp` SDK** for Streamable HTTP (verified live).
- **Next.js + TypeScript** frontend.
- **pgvector**: deferred. v0.1.0 uses keyword-overlap memory retrieval so the
  system does not depend on an unverified embedding model/dimensions.

## Process model

v0.1.0 runs tasks as background asyncio tasks in the API process. The
permission scope is deliberately read-only-with-approval, so in-process
execution is acceptable; a dedicated worker container is documented as the
next hardening step in docs/SECURITY.md.
