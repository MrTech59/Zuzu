"""Memory endpoints: list, search and delete durable memories."""

from __future__ import annotations

import logging
import uuid as uuidlib

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from zuzu.api.routes.chat import _ensure_default_user
from zuzu.config import Settings, get_settings
from zuzu.db.engine import get_session
from zuzu.memory import service as memory_svc

logger = logging.getLogger("zuzu.api.memories")
router = APIRouter(prefix="/api/v1", tags=["memories"])


class MemoryOut(BaseModel):
    id: uuidlib.UUID
    kind: str
    content: str
    source: str
    created_at: str


class MemoryCreateIn(BaseModel):
    content: str = Field(min_length=1)
    kind: str = Field(default="fact", max_length=32)


def _memory_out(m) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        kind=m.kind,
        content=m.content,
        source=m.source,
        created_at=m.created_at.isoformat() + "Z",
    )


@router.get("/memories")
async def list_memories(
    query: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    user_id = await _ensure_default_user(session)
    rows = await memory_svc.list_memories(session, user_id, limit=limit, offset=offset, query=query)
    return {"memories": [_memory_out(m).model_dump(mode="json") for m in rows]}


@router.post("/memories", status_code=201)
async def create_memory(
    body: MemoryCreateIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    user_id = await _ensure_default_user(session)
    mem = await memory_svc.create_memory(
        session,
        user_id,
        body.content,
        kind=body.kind,
        max_chars=settings.memory_max_chars,
    )
    return _memory_out(mem).model_dump(mode="json")


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: uuidlib.UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    user_id = await _ensure_default_user(session)
    await memory_svc.delete_memory(session, user_id, memory_id)
    return {"deleted": str(memory_id)}
