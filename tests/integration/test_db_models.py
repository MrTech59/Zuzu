"""Database model + persistence tests (SQLite via aiosqlite)."""

from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from zuzu.db.base import utcnow
from zuzu.db.engine import get_session_factory
from zuzu.db.models import (
    Approval,
    AuditEvent,
    Conversation,
    Memory,
    Message,
    Task,
    TaskStatus,
    TaskStep,
    User,
)


@pytest.mark.asyncio
async def test_user_conversation_message_roundtrip(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = User(username="alice")
        session.add(user)
        await session.flush()
        conv = Conversation(user_id=user.id, title="Test")
        session.add(conv)
        await session.flush()
        session.add(Message(conversation_id=conv.id, role="user", content="hi"))
        session.add(Message(conversation_id=conv.id, role="assistant", content="hello"))
        await session.commit()

        fetched = (
            (await session.execute(select(Message).where(Message.conversation_id == conv.id)))
            .scalars()
            .all()
        )
        assert len(fetched) == 2
        assert fetched[0].created_at is not None
        # Deleting the conversation cascades to messages.
        await session.delete(conv)
        await session.commit()
        remaining = (
            (await session.execute(select(Message).where(Message.conversation_id == conv.id)))
            .scalars()
            .all()
        )
        assert remaining == []


@pytest.mark.asyncio
async def test_memory_roundtrip_and_deletion(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = User(username="bob")
        session.add(user)
        await session.flush()
        mem = Memory(user_id=user.id, content="Remembers things.")
        session.add(mem)
        await session.commit()

        rows = (await session.execute(select(Memory))).scalars().all()
        assert len(rows) == 1
        await session.delete(rows[0])
        await session.commit()
        assert (await session.execute(select(Memory))).scalars().all() == []


@pytest.mark.asyncio
async def test_task_with_steps_and_approvals_cascade(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = User(username="carol")
        session.add(user)
        await session.flush()
        task = Task(
            user_id=user.id,
            agent="researcher",
            title="T",
            instruction="Do research",
            status=TaskStatus.queued,
        )
        session.add(task)
        await session.flush()
        session.add(TaskStep(task_id=task.id, position=0, name="read", status="pending"))
        session.add(
            Approval(
                task_id=task.id,
                action="mcp_tool",
                resource="browser_navigate",
                expires_at=utcnow(),
            )
        )
        await session.commit()

        fetched = (
            await session.execute(
                select(Task)
                .where(Task.id == task.id)
                .options(selectinload(Task.steps), selectinload(Task.approvals))
            )
        ).scalar_one()
        assert len(fetched.steps) == 1
        assert len(fetched.approvals) == 1

        await session.delete(fetched)
        await session.commit()
        assert (await session.execute(select(TaskStep))).scalars().all() == []
        assert (await session.execute(select(Approval))).scalars().all() == []


@pytest.mark.asyncio
async def test_uuid_pk_and_utc_timestamps(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = User(username="dave")
        session.add(user)
        await session.flush()
        assert isinstance(user.id, uuidlib.UUID)
        assert user.created_at.tzinfo is None  # naive UTC
        await session.commit()


@pytest.mark.asyncio
async def test_audit_event_persistence(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        event = AuditEvent(event_type="test.event", actor="tester", detail='{"a": 1}')
        session.add(event)
        await session.commit()
        rows = (await session.execute(select(AuditEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].event_type == "test.event"
