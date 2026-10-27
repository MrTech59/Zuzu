"""Approval service.

Approvals are the human checkpoint for consequential actions. Guarantees:
- Bound to the exact action (kind, tool, resource, params fingerprint).
- Single-use: consuming an approval marks it used and it cannot be reused.
- Expiring: expired approvals are rejected on decision or consumption.
- Changed-action rejection: a decision for a *different* action fingerprint
  is invalid.
- The model can never approve its own actions; decisions only come through
  the authenticated API.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zuzu.config import get_settings
from zuzu.db.models import Approval, ApprovalStatus
from zuzu.errors import ConflictError, NotFoundError
from zuzu.policy.engine import Action

APPROVAL_EXPIRED_MESSAGE = "Approval expired."


def fingerprint(action: Action) -> str:
    """Stable fingerprint of the exact action (kind, tool, resource, params)."""
    payload = json.dumps(
        {
            "kind": action.kind,
            "tool": action.tool or "",
            "resource": action.resource or "",
            "params": action.params,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def create_approval(
    session: AsyncSession,
    *,
    task_id: Any,
    action: Action,
    reason: str | None = None,
    requested_by: str | None = None,
    step_id: Any | None = None,
    ttl_seconds: int | None = None,
) -> Approval:
    """Create a pending, expiring approval bound to an exact action.

    The full action (tool, resource, params) is serialized in `params` so the
    exact action can be reconstructed for single-use consumption without any
    ambiguity.
    """
    if ttl_seconds is None:
        ttl_seconds = get_settings().approval_ttl_seconds
    approval = Approval(
        task_id=task_id,
        step_id=step_id,
        status=ApprovalStatus.pending,
        action=action.kind,
        resource=action.resource or (action.tool or ""),
        params=json.dumps(
            {"tool": action.tool, "resource": action.resource, "params": action.params},
            ensure_ascii=False,
            default=str,
        ),
        params_hash=fingerprint(action),
        reason=reason,
        requested_by=requested_by,
        created_at=utcnow_naive(),
        expires_at=utcnow_naive() + timedelta(seconds=ttl_seconds),
    )
    session.add(approval)
    await session.flush()
    return approval


def action_from_approval(approval: Approval) -> Action:
    """Reconstruct the exact Action bound to an approval."""
    data = json.loads(approval.params or "{}")
    return Action(
        kind=approval.action,
        tool=data.get("tool"),
        resource=data.get("resource"),
        params=data.get("params") or {},
    )


async def _expire_if_needed(approval: Approval) -> None:
    if approval.status is ApprovalStatus.pending and approval.expires_at <= utcnow_naive():
        approval.status = ApprovalStatus.expired


async def decide_approval(
    session: AsyncSession,
    approval_id: Any,
    *,
    approve: bool,
    decided_by: str,
    proposed_action: Action | None = None,
) -> Approval:
    """Decide a pending approval.

    When `proposed_action` is given, the decision is only valid if its
    fingerprint matches the approval's — rejecting decisions made against
    changed actions.
    """
    approval = await session.get(Approval, approval_id)
    if approval is None:
        raise NotFoundError("Approval not found.")
    if approval.status is not ApprovalStatus.pending:
        raise ConflictError(f"Approval is not pending (status={approval.status.value}).")
    await _expire_if_needed(approval)
    if approval.status is ApprovalStatus.expired:
        raise ConflictError(APPROVAL_EXPIRED_MESSAGE)

    if proposed_action is not None and fingerprint(proposed_action) != approval.params_hash:
        raise ConflictError(
            "The proposed action has changed since the approval was requested; "
            "the stale decision is rejected."
        )

    approval.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    approval.decided_by = decided_by
    approval.decided_at = utcnow_naive()
    await session.flush()
    return approval


async def consume_approval(
    session: AsyncSession,
    approval_id: Any,
    *,
    action: Action,
) -> Approval:
    """Consume a single-use approval just before executing its exact action.

    Raises ConflictError when the approval is missing, rejected, expired, or
    when the action no longer matches the approved fingerprint.
    """
    approval = await session.get(Approval, approval_id)
    if approval is None:
        raise NotFoundError("Approval not found.")
    if approval.status is not ApprovalStatus.approved:
        raise ConflictError(f"Approval is not approved (status={approval.status.value}).")
    if approval.expires_at <= utcnow_naive():
        approval.status = ApprovalStatus.expired
        await session.flush()
        raise ConflictError(APPROVAL_EXPIRED_MESSAGE)
    if fingerprint(action) != approval.params_hash:
        raise ConflictError(
            "Action parameters changed after approval; approval is no longer valid."
        )
    # Single-use consumption.
    approval.status = ApprovalStatus.used
    approval.decided_at = approval.decided_at or utcnow_naive()
    await session.flush()
    return approval


async def pending_approvals_for_task(session: AsyncSession, task_id: Any) -> list[Approval]:
    stmt = select(Approval).where(
        Approval.task_id == task_id, Approval.status == ApprovalStatus.pending
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def expire_stale(session: AsyncSession) -> int:
    """Mark pending-but-expired approvals as expired. Returns count."""
    stmt = select(Approval).where(Approval.status == ApprovalStatus.pending)
    rows = (await session.execute(stmt)).scalars().all()
    n = 0
    for a in rows:
        if a.expires_at <= utcnow_naive():
            a.status = ApprovalStatus.expired
            n += 1
    if n:
        await session.flush()
    return n
