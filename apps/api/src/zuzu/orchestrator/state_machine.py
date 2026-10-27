"""Task state machine.

States: queued → planning → running → awaiting_approval → running → succeeded
Also: failed, cancelled (from any non-terminal state).

Validation rules:
- Transitions must follow TRANSITIONS.
- A task may be marked succeeded only when every required step has succeeded
  and no approval remains pending.
- Cancellation is permitted from any non-terminal state.
"""

from __future__ import annotations

import enum

from zuzu.errors import ConflictError


class TaskStatus(enum.StrEnum):
    queued = "queued"
    planning = "planning"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATES = frozenset({TaskStatus.succeeded, TaskStatus.failed, TaskStatus.cancelled})

TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.queued: frozenset(
        {TaskStatus.planning, TaskStatus.running, TaskStatus.failed, TaskStatus.cancelled}
    ),
    TaskStatus.planning: frozenset({TaskStatus.running, TaskStatus.failed, TaskStatus.cancelled}),
    TaskStatus.running: frozenset(
        {
            TaskStatus.awaiting_approval,
            TaskStatus.succeeded,
            TaskStatus.failed,
            TaskStatus.cancelled,
        }
    ),
    TaskStatus.awaiting_approval: frozenset(
        {TaskStatus.running, TaskStatus.failed, TaskStatus.cancelled}
    ),
    TaskStatus.succeeded: frozenset(),
    TaskStatus.failed: frozenset(),
    TaskStatus.cancelled: frozenset(),
}


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Raise ConflictError when the transition is not permitted."""
    if current is target:
        return
    allowed = TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ConflictError(f"Invalid task transition: {current.value} -> {target.value}.")


def assert_can_succeed(
    *,
    step_statuses: list[str],
    pending_approvals: int,
) -> None:
    """Guard for the running -> succeeded transition.

    Raises ConflictError unless:
    - every step is in a terminal success-like state (succeeded or skipped)
      with at least one step, and
    - no approval is pending.
    """
    if pending_approvals > 0:
        raise ConflictError("Task cannot succeed while approvals are pending.")
    if not step_statuses:
        raise ConflictError("Task cannot succeed without at least one completed step.")
    bad = [s for s in step_statuses if s not in ("succeeded", "skipped")]
    if bad:
        raise ConflictError(f"Task cannot succeed with steps in state(s): {sorted(set(bad))}.")
