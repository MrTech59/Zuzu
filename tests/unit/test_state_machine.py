"""Task state machine tests."""

from __future__ import annotations

import pytest

from zuzu.errors import ConflictError
from zuzu.orchestrator.state_machine import (
    TERMINAL_STATES,
    TaskStatus,
    assert_can_succeed,
    validate_transition,
)


def test_happy_path_transitions() -> None:
    validate_transition(TaskStatus.queued, TaskStatus.planning)
    validate_transition(TaskStatus.planning, TaskStatus.running)
    validate_transition(TaskStatus.running, TaskStatus.awaiting_approval)
    validate_transition(TaskStatus.awaiting_approval, TaskStatus.running)
    validate_transition(TaskStatus.running, TaskStatus.succeeded)


def test_invalid_transitions_rejected() -> None:
    with pytest.raises(ConflictError):
        validate_transition(TaskStatus.queued, TaskStatus.succeeded)
    with pytest.raises(ConflictError):
        validate_transition(TaskStatus.queued, TaskStatus.awaiting_approval)
    with pytest.raises(ConflictError):
        validate_transition(TaskStatus.succeeded, TaskStatus.running)
    with pytest.raises(ConflictError):
        validate_transition(TaskStatus.failed, TaskStatus.succeeded)
    with pytest.raises(ConflictError):
        validate_transition(TaskStatus.cancelled, TaskStatus.running)


def test_cancellation_allowed_from_any_active_state() -> None:
    for state in (
        TaskStatus.queued,
        TaskStatus.planning,
        TaskStatus.running,
        TaskStatus.awaiting_approval,
    ):
        validate_transition(state, TaskStatus.cancelled)


def test_success_requires_all_steps_done_and_no_pending_approvals() -> None:
    assert_can_succeed(step_statuses=["succeeded", "succeeded"], pending_approvals=0)

    with pytest.raises(ConflictError):
        assert_can_succeed(step_statuses=["succeeded", "running"], pending_approvals=0)
    with pytest.raises(ConflictError):
        assert_can_succeed(step_statuses=["succeeded"], pending_approvals=1)
    with pytest.raises(ConflictError):
        assert_can_succeed(step_statuses=[], pending_approvals=0)


def test_terminal_states_are_terminal() -> None:
    for state in TERMINAL_STATES:
        assert not TRANSITIONS_OF(state)


def TRANSITIONS_OF(state: TaskStatus) -> frozenset:
    from zuzu.orchestrator.state_machine import TRANSITIONS

    return TRANSITIONS[state]
