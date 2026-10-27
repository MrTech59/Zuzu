"""Memory service.

Durable, user-facing knowledge items, deliberately separate from conversation
history and task records:
- memories: long-lived facts the user explicitly wants remembered; retrievable
  in the system prompt; deletable at any time.
- messages: transient conversation history.
- tasks: orchestration records.

v0.1.0 uses keyword-overlap retrieval backed purely by Postgres. Vector
(pgvector) retrieval is intentionally deferred until an embedding model and
its dimensions are verified; see docs/DATABASE.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zuzu.db.models import Memory
from zuzu.errors import NotFoundError, ValidationError

logger = logging.getLogger("zuzu.memory")

_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have how i in is it its of on or "
    "that the this to was what when where which who with you your".split()
)


def _tokenize(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in _STOPWORDS and len(t) > 1
    }


def relevance_score(query_tokens: set[str], memory_text: str) -> float:
    """Keyword overlap score in [0, 1]."""
    if not query_tokens:
        return 0.0
    memory_tokens = _tokenize(memory_text)
    if not memory_tokens:
        return 0.0
    return len(query_tokens & memory_tokens) / len(query_tokens)


async def create_memory(
    session: AsyncSession,
    user_id: Any,
    content: str,
    *,
    kind: str = "fact",
    source: str = "user",
    max_chars: int = 4000,
) -> Memory:
    content = content.strip()
    if not content:
        raise ValidationError("Memory content must not be empty.")
    if len(content) > max_chars:
        raise ValidationError(f"Memory content exceeds {max_chars} characters.")
    mem = Memory(user_id=user_id, content=content, kind=kind, source=source)
    session.add(mem)
    await session.flush()
    return mem


async def list_memories(
    session: AsyncSession,
    user_id: Any,
    *,
    limit: int = 100,
    offset: int = 0,
    query: str | None = None,
) -> list[Memory]:
    """List memories, optionally filtered by keyword relevance > 0."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    stmt = stmt.order_by(Memory.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    if query:
        q_tokens = _tokenize(query)
        rows = [r for r in rows if relevance_score(q_tokens, r.content) > 0]
    return list(rows)


async def retrieve_relevant(
    session: AsyncSession,
    user_id: Any,
    query: str,
    *,
    limit: int = 5,
) -> list[Memory]:
    """Top memories by keyword overlap with the query."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()
    q_tokens = _tokenize(query)
    scored = sorted(
        ((relevance_score(q_tokens, r.content), r) for r in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [r for score, r in scored[:limit] if score > 0]


async def delete_memory(session: AsyncSession, user_id: Any, memory_id: Any) -> None:
    mem = await session.get(Memory, memory_id)
    if mem is None or mem.user_id != user_id:
        raise NotFoundError("Memory not found.")
    await session.execute(sa_delete(Memory).where(Memory.id == memory_id))


async def count_memories(session: AsyncSession, user_id: Any) -> int:
    stmt = select(func.count()).select_from(Memory).where(Memory.user_id == user_id)
    return int((await session.execute(stmt)).scalar_one())
