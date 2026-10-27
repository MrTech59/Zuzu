"""Approval semantics tests: expiry, single-use, changed-action rejection."""

from __future__ import annotations

import uuid as uuidlib
from datetime import timedelta

import pytest

from zuzu.db.engine import get_session_factory
from zuzu.db.models import ApprovalStatus
from zuzu.errors import ConflictError, NotFoundError
from zuzu.orchestrator.approvals import (
    action_from_approval,
    consume_approval,
    create_approval,
    decide_approval,
    expire_stale,
    fingerprint,
)
from zuzu.policy.engine import Action


@pytest.fixture()
def action() -> Action:
    return Action(
        kind="mcp_tool",
        tool="browser_navigate",
        resource=None,
        params={"url": "https://example.com"},
    )


@pytest.mark.asyncio
async def test_approve_then_consume_is_single_use(db_schema, action: Action) -> None:
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u1")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action)
        assert approval.status.value == "pending"

        decided = await decide_approval(session, approval.id, approve=True, decided_by="user")
        assert decided.status.value == "approved"

        consumed = await consume_approval(session, approval.id, action=action)
        # Consumption marks it used: a consumed approval cannot be reused.
        assert consumed.status.value == "used"

        # Second consumption must fail.
        with pytest.raises(ConflictError):
            await consume_approval(session, approval.id, action=action)
        await session.rollback()


@pytest.mark.asyncio
async def test_rejected_approval_cannot_be_consumed(db_schema, action: Action) -> None:
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u2")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action)
        await decide_approval(session, approval.id, approve=False, decided_by="user")
        with pytest.raises(ConflictError):
            await consume_approval(session, approval.id, action=action)
        await session.rollback()


@pytest.mark.asyncio
async def test_expired_approval_rejected(db_schema, action: Action) -> None:
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u3")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action, ttl_seconds=5)
        approval.expires_at = approval.expires_at - timedelta(seconds=10)
        await session.flush()

        # Decision after expiry is rejected.
        with pytest.raises(ConflictError, match="expired"):
            await decide_approval(session, approval.id, approve=True, decided_by="user")
        # Consumption after expiry is rejected.
        approval.status = ApprovalStatus.approved
        approval.decided_at = None
        await session.flush()
        with pytest.raises(ConflictError, match="expired"):
            await consume_approval(session, approval.id, action=action)
        await session.rollback()


@pytest.mark.asyncio
async def test_changed_action_rejected_at_consumption(db_schema, action: Action) -> None:
    """The executed action must match the approved fingerprint exactly."""
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u4")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action)
        await decide_approval(session, approval.id, approve=True, decided_by="user")

        changed = Action(
            kind="mcp_tool",
            tool="browser_navigate",
            params={"url": "https://evil.example.com"},  # changed target!
        )
        with pytest.raises(ConflictError, match="changed"):
            await consume_approval(session, approval.id, action=changed)
        await session.rollback()


@pytest.mark.asyncio
async def test_fingerprint_binds_kind_tool_resource_and_params(
    db_schema,
) -> None:
    a1 = Action(kind="mcp_tool", tool="t", resource=None, params={"x": 1})
    a2 = Action(kind="mcp_tool", tool="t", resource=None, params={"x": 1})
    a3 = Action(kind="mcp_tool", tool="t", resource=None, params={"x": 2})
    a4 = Action(kind="mcp_tool", tool="other", resource=None, params={"x": 1})
    a5 = Action(kind="file_write", tool="t", resource=None, params={"x": 1})
    assert fingerprint(a1) == fingerprint(a2)
    assert fingerprint(a1) != fingerprint(a3)
    assert fingerprint(a1) != fingerprint(a4)
    assert fingerprint(a1) != fingerprint(a5)


@pytest.mark.asyncio
async def test_action_roundtrip_from_approval(db_schema, action: Action) -> None:
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u5")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action)
        rebuilt = action_from_approval(approval)
        assert fingerprint(rebuilt) == fingerprint(action)
        await session.rollback()


@pytest.mark.asyncio
async def test_expire_stale_marks_expired(db_schema, action: Action) -> None:
    factory = get_session_factory()
    async with factory() as session:
        from zuzu.db.models import Task, User

        user = User(username="u6")
        session.add(user)
        await session.flush()
        task = Task(user_id=user.id, agent="researcher", title="t", instruction="i")
        session.add(task)
        await session.flush()

        approval = await create_approval(session, task_id=task.id, action=action, ttl_seconds=5)
        approval.expires_at = approval.expires_at - timedelta(seconds=10)
        await session.flush()

        count = await expire_stale(session)
        assert count == 1
        assert approval.status.value == "expired"
        await session.rollback()


@pytest.mark.asyncio
async def test_decide_unknown_approval_404(db_schema) -> None:
    factory = get_session_factory()
    async with factory() as session:
        with pytest.raises(NotFoundError):
            await decide_approval(
                session,
                uuidlib.UUID(int=0),
                approve=True,
                decided_by="user",
            )
