# Zuzu Database

PostgreSQL 16 is the target. Migrations: Alembic (`migrations/versions`).
SQLite (aiosqlite) is supported for tests/offline dev.

## Schema (migration `0001_initial`)

| Table | Purpose | Notes |
| --- | --- | --- |
| users | user identity | unique username |
| conversations | chat threads | FK users, ON DELETE CASCADE |
| messages | conversation turns | FK conversations, indexed (conversation_id, created_at) |
| memories | durable knowledge items | FK users; kind/source; deletable individually |
| tasks | orchestration tasks | status enum-as-string; failure_reason; result JSON |
| task_steps | per-step records | FK tasks; position-ordered |
| approvals | exact-action checkpoints | params_hash fingerprint; expires_at; single-use (`used`) |
| audit_events | security-relevant log | redacted detail JSON; append-only by convention |

Conventions: UUID PKs (native `uuid` on Postgres, `CHAR(32)`-hex on SQLite via
SQLAlchemy `Uuid`), UTC timestamps (naive UTC), explicit FK `ondelete`, indexes
for common queries.

## Boundaries

- **messages** = transient conversation history; never treated as durable
  knowledge.
- **memories** = durable user-owned facts; retrieval via keyword overlap
  (`memory/service.py`), deletion via `DELETE /api/v1/memories/{id}`.
- **tasks/steps/approvals** = orchestration records, separate from chat.

## Vector search (deferred)

pgvector is intentionally NOT enabled in v0.1.0: the embedding model and its
vector dimensions have not been verified in this environment. When an
embedding provider is chosen, add a migration that (1) creates the pgvector
extension, (2) adds an `embedding vector(N)` column with the verified
dimension N, (3) adds an ivfflat/hnsw index. The keyword-based implementation
keeps development unblocked meanwhile.

## Operating

```powershell
python -m alembic upgrade head      # apply
python -m alembic downgrade base    # roll back (dev only)
```

Backups: `scripts/backup.sh` (pg_dump -Fc, 14-day retention). Restore:

```bash
pg_restore -U zuzu -d zuzu --clean zuzu-db-<stamp>.dump
```

## Tests

- `tests/integration/test_db_models.py` — model round-trips, cascades, UUID/UTC.
- `tests/integration/test_migrations.py` — clean upgrade, upgrade/downgrade
  round-trip.
- `tests/integration/test_memories.py` — retrieval and deletion boundaries.
