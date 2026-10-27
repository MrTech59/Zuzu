"""Task and approval endpoints."""

from __future__ import annotations

import logging
import uuid as uuidlib

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from zuzu.config import Settings, get_settings
from zuzu.db.engine import get_session, get_session_factory
from zuzu.db.models import Approval, ApprovalStatus, Task, TaskStatus, TaskStep
from zuzu.errors import ConflictError, NotFoundError, ValidationError
from zuzu.orchestrator import approvals as approvals_svc
from zuzu.orchestrator.profiles import POLICY_DIR, load_profiles
from zuzu.orchestrator.runner import TaskRunner, is_running
from zuzu.policy.engine import PolicyEngine, load_policy_from_files

logger = logging.getLogger("zuzu.api.tasks")
router = APIRouter(prefix="/api/v1", tags=["tasks"])

KNOWN_AGENTS = ("researcher", "developer", "tester", "homelab-observer")


class TaskCreateIn(BaseModel):
    agent: str
    title: str = Field(min_length=1, max_length=256)
    instruction: str = Field(min_length=1)
    conversation_id: uuidlib.UUID | None = None


class StepOut(BaseModel):
    id: uuidlib.UUID
    position: int
    name: str
    tool: str | None
    status: str
    detail: str | None


class ApprovalOut(BaseModel):
    id: uuidlib.UUID
    status: str
    action: str
    resource: str
    reason: str | None
    created_at: str
    expires_at: str


class TaskOut(BaseModel):
    id: uuidlib.UUID
    agent: str
    title: str
    status: str
    failure_reason: str | None
    step_count: int
    max_steps: int
    result: str | None
    created_at: str
    finished_at: str | None
    running: bool
    steps: list[StepOut] = []
    approvals: list[ApprovalOut] = []


def _approval_out(a: Approval) -> ApprovalOut:
    return ApprovalOut(
        id=a.id,
        status=a.status.value if isinstance(a.status, ApprovalStatus) else str(a.status),
        action=a.action,
        resource=a.resource,
        reason=a.reason,
        created_at=a.created_at.isoformat() + "Z",
        expires_at=a.expires_at.isoformat() + "Z",
    )


def _task_out(task: Task, steps: list[TaskStep], approvals: list[Approval]) -> TaskOut:
    return TaskOut(
        id=task.id,
        agent=task.agent,
        title=task.title,
        status=task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
        failure_reason=task.failure_reason,
        step_count=task.step_count,
        max_steps=task.max_steps,
        result=task.result,
        created_at=task.created_at.isoformat() + "Z",
        finished_at=task.finished_at.isoformat() + "Z" if task.finished_at else None,
        running=is_running(task.id),
        steps=[
            StepOut(
                id=s.id,
                position=s.position,
                name=s.name,
                tool=s.tool,
                status=s.status,
                detail=s.detail,
            )
            for s in steps
        ],
        approvals=[_approval_out(a) for a in approvals],
    )


def get_policy_engine() -> PolicyEngine:
    return load_policy_from_files(str(POLICY_DIR / "tools.yaml"), str(POLICY_DIR / "agents.yaml"))


def get_runner(settings: Settings = Depends(get_settings)) -> TaskRunner:
    from zuzu.ai.factory import get_provider

    return TaskRunner(
        session_factory=get_session_factory(),
        policy=get_policy_engine(),
        provider=get_provider(settings),
        settings=settings,
    )


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreateIn,
    session=Depends(get_session),
    runner: TaskRunner = Depends(get_runner),
    settings: Settings = Depends(get_settings),
) -> dict:
    if body.agent not in KNOWN_AGENTS:
        raise ValidationError(f"Unknown agent '{body.agent}'.")
    profiles = load_profiles()
    profile = profiles[body.agent]

    from zuzu.api.routes.chat import _ensure_default_user

    user_id = await _ensure_default_user(session)

    if len(body.instruction) > 20000:
        raise ValidationError("Instruction too long (max 20000 characters).")

    task = Task(
        user_id=user_id,
        conversation_id=body.conversation_id,
        agent=body.agent,
        title=body.title,
        instruction=body.instruction,
        status=TaskStatus.queued,
        max_steps=min(profile.max_steps, settings.task_max_steps),
    )
    session.add(task)
    await session.flush()

    from zuzu.audit.service import record_event

    await record_event(
        session,
        event_type="task.created",
        actor="user",
        task_id=str(task.id),
        subject=body.agent,
        detail={"title": body.title},
    )
    await session.commit()
    await runner.start_task(task.id)

    fresh = await session.get(Task, task.id)
    steps = (
        (await session.execute(select(TaskStep).where(TaskStep.task_id == task.id))).scalars().all()
    )
    appr = (
        (await session.execute(select(Approval).where(Approval.task_id == task.id))).scalars().all()
    )
    return _task_out(fresh, list(steps), list(appr)).model_dump(mode="json")


@router.get("/tasks")
async def list_tasks(session=Depends(get_session)) -> dict:
    stmt = select(Task).order_by(Task.created_at.desc()).limit(100)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for t in rows:
        out.append(
            {
                "id": str(t.id),
                "agent": t.agent,
                "title": t.title,
                "status": t.status.value if isinstance(t.status, TaskStatus) else str(t.status),
                "created_at": t.created_at.isoformat() + "Z",
                "step_count": t.step_count,
                "failure_reason": t.failure_reason,
            }
        )
    return {"tasks": out}


@router.get("/tasks/{task_id}")
async def get_task(task_id: uuidlib.UUID, session=Depends(get_session)) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    steps = (
        (
            await session.execute(
                select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.position)
            )
        )
        .scalars()
        .all()
    )
    appr = (
        (await session.execute(select(Approval).where(Approval.task_id == task_id))).scalars().all()
    )
    return _task_out(task, list(steps), list(appr)).model_dump(mode="json")


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: uuidlib.UUID,
    session=Depends(get_session),
    runner: TaskRunner = Depends(get_runner),
) -> dict:
    await runner.cancel_task(task_id)
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    return {
        "id": str(task.id),
        "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
    }


class ApprovalDecisionIn(BaseModel):
    approve: bool
    decided_by: str = Field(default="user", max_length=128)
    # Optional proof-of-what-you-are-deciding: the API rejects stale decisions
    # when the action no longer matches what was requested.
    confirm_action: str | None = None


@router.get("/approvals")
async def list_approvals(
    session=Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    await approvals_svc.expire_stale(session)
    stmt = (
        select(Approval)
        .where(
            Approval.status.in_(
                [
                    ApprovalStatus.pending,
                    ApprovalStatus.approved,
                    ApprovalStatus.rejected,
                    ApprovalStatus.expired,
                ]
            )
        )
        .order_by(Approval.created_at.desc())
        .limit(100)
    )
    rows = (await session.execute(stmt)).scalars().all()
    await session.commit()
    return {"approvals": [_approval_out(a).model_dump(mode="json") for a in rows]}


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: uuidlib.UUID,
    body: ApprovalDecisionIn,
    session=Depends(get_session),
    runner: TaskRunner = Depends(get_runner),
    settings: Settings = Depends(get_settings),
) -> dict:
    approval = await session.get(Approval, approval_id)
    if approval is None:
        raise NotFoundError("Approval not found.")

    # Decision-level stale-action check (defense in depth; the binding check
    # against the exact fingerprint happens again at execution/consumption).
    if body.confirm_action is not None and body.confirm_action != approval.action:
        raise ConflictError(
            "The proposed action has changed since the approval was requested; "
            "the stale decision is rejected."
        )

    decided = await approvals_svc.decide_approval(
        session,
        approval_id,
        approve=body.approve,
        decided_by=body.decided_by,
    )
    from zuzu.audit.service import record_event

    await record_event(
        session,
        event_type="approval.decided",
        actor=body.decided_by,
        task_id=str(approval.task_id),
        subject=approval.action,
        outcome=decided.status.value,
        detail={"approve": body.approve},
    )
    await session.commit()

    # Resume the paused task, passing the decided approval explicitly (both
    # approve and reject paths resolve the pause).
    await runner.resume_task(approval.task_id, decided.id)

    return {"id": str(decided.id), "status": decided.status.value}


@router.get("/agents")
async def list_agents() -> dict:
    profiles = load_profiles()
    return {
        "agents": [
            {
                "name": name,
                "description": p.description,
                "max_steps": p.max_steps,
                "timeout_seconds": p.timeout_seconds,
                "output_format": p.output_format,
            }
            for name, p in profiles.items()
        ]
    }
