"""Task runner: executes a task through its lifecycle with policy enforcement.

Design:
- Tasks run as background asyncio tasks in the API process (v0.1.0; a separate
  worker container is a documented future step and is not required for the
  current read-only permission scope).
- Every step passes through the policy engine BEFORE execution.
- Steps needing approval pause the task in `awaiting_approval` with a persisted
  approval bound to the exact action fingerprint.
- Approval decisions arrive through the API; `resume_task` continues after a
  decision. Approval consumption is single-use and fingerprint-checked.
- Bounded by max steps and a wall-clock deadline; cancellation is checked
  between steps and honoured immediately for running awaits.
- Honest failures: any unavailability (MCP down, provider error) marks the
  task failed with a clear reason. Nothing pretends success.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zuzu.ai.base import ChatMessage, ChatRequest
from zuzu.audit.service import record_event, utcnow_naive
from zuzu.config import Settings
from zuzu.db.models import Approval, ApprovalStatus, Task, TaskStatus, TaskStep
from zuzu.errors import ConflictError, NotFoundError, PolicyDeniedError, ProviderError
from zuzu.orchestrator.approvals import (
    action_from_approval,
    consume_approval,
    create_approval,
)
from zuzu.orchestrator.state_machine import (
    TERMINAL_STATES,
    assert_can_succeed,
    validate_transition,
)
from zuzu.orchestrator.state_machine import (
    TaskStatus as SMTaskStatus,
)
from zuzu.policy.engine import Action, Decision, PolicyEngine

logger = logging.getLogger("zuzu.orchestrator.runner")

# In-memory registry of running asyncio tasks keyed by task id (UUID str).
_running: dict[str, asyncio.Task[None]] = {}


def _fmt_plan_prompt(instruction: str, agent_name: str) -> str:
    return (
        "Create an execution plan for the following task. Reply ONLY with JSON "
        "(no prose, no code fences) matching exactly:\n"
        '{"steps": [{"name": str, "tool": str|null, "kind": str, "params": object}]}\n'
        'Valid kinds: "mcp_tool" (use an approved browser tool) or "respond" '
        "(compose the final answer). Keep it under 8 steps.\n\n"
        f"Agent: {agent_name}\nTask instruction: {instruction}"
    )


class TaskRunner:
    def __init__(
        self,
        session_factory,
        policy: PolicyEngine,
        provider: Any,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.policy = policy
        self.provider = provider
        self.settings = settings

    # ------------------------------------------------------------------ start
    async def start_task(self, task_id: Any) -> None:
        """Kick off background execution of a queued task."""
        existing = _running.get(str(task_id))
        if existing is not None and not existing.done():
            raise ConflictError("Task is already running.")
        _running[str(task_id)] = asyncio.create_task(self._run_wrapper(task_id))

    async def cancel_task(self, task_id: Any) -> None:
        """Cancel a task if it is running; always update DB status."""
        t = _running.pop(str(task_id), None)
        if t is not None:
            t.cancel()
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task not found.")
            if task.status in TERMINAL_STATES:
                return
            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.cancelled)
            task.status = SMTaskStatus.cancelled
            task.finished_at = utcnow_naive()
            task.failure_reason = task.failure_reason or "Cancelled by user."
            await record_event(
                session,
                event_type="task.cancelled",
                actor="user",
                task_id=str(task.id),
                detail={},
            )
            await session.commit()

    # ------------------------------------------------------------------- loop
    async def _run_wrapper(self, task_id: Any) -> None:
        try:
            await self._run(task_id)
        except asyncio.CancelledError:
            # DB status already set by cancel_task.
            raise
        except Exception as exc:  # noqa: BLE001 - background task safety net
            logger.exception("Task %s crashed: %s", task_id, exc)
            async with self.session_factory() as session:
                task = await session.get(Task, task_id)
                if task is not None and task.status not in TERMINAL_STATES:
                    task.status = TaskStatus.failed
                    task.finished_at = utcnow_naive()
                    task.failure_reason = f"Internal error: {type(exc).__name__}"
                    await session.commit()

    async def _fresh_task(self, session: AsyncSession, task_id: Any) -> Task:
        task = await session.get(Task, task_id)
        assert task is not None
        return task

    async def _run(self, task_id: Any) -> None:
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task not found.")
            if task.status != TaskStatus.queued:
                raise ConflictError(f"Task is not queued (status={task.status.value}).")
            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.planning)
            task.status = TaskStatus.planning
            task.started_at = utcnow_naive()
            await record_event(
                session, event_type="task.started", actor=task.agent, task_id=str(task.id)
            )
            await session.commit()

        deadline = utcnow_naive() + timedelta(seconds=self.settings.task_timeout_seconds)

        async with self.session_factory() as session:
            steps = await self._plan(session, task_id)
            task = await self._fresh_task(session, task_id)
            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.running)
            task.status = TaskStatus.running
            await session.commit()

            await self._execute_steps(session, task_id, steps, deadline)

    async def _execute_steps(
        self,
        session: AsyncSession,
        task_id: Any,
        steps: list[TaskStep],
        deadline: Any,
    ) -> None:
        """Run steps in order with policy checks.

        Returns when the task pauses (awaiting_approval), is cancelled, fails,
        or all steps are done (task left in running for _try_succeed).
        """
        tool_outputs: list[dict[str, Any]] = []
        for step in steps:
            await self._check_deadline(task_id, deadline)
            task = await self._fresh_task(session, task_id)
            if task.status in (
                TaskStatus.cancelled,
                TaskStatus.failed,
                TaskStatus.awaiting_approval,
            ):
                return
            if task.step_count >= task.max_steps:
                await self._fail(session, task, reason=f"Step limit reached ({task.max_steps}).")
                return

            step.status = "running"
            await record_event(
                session,
                event_type="step.started",
                actor=task.agent,
                task_id=str(task.id),
                subject=step.name,
                detail={"tool": step.tool, "position": step.position},
            )
            await session.commit()

            try:
                paused = await self._execute_step(session, task, step, tool_outputs)
            except asyncio.CancelledError:
                raise
            except PolicyDeniedError as exc:
                step.status = "failed"
                step.detail = str(exc.message)
                await self._fail(session, task, reason=exc.message)
                return
            except Exception as exc:  # noqa: BLE001
                step.status = "failed"
                step.detail = str(exc)[:500]
                await self._fail(session, task, reason=f"Step '{step.name}' failed: {exc}")
                return

            if paused:
                # Task is now awaiting_approval.
                return

        task = await self._fresh_task(session, task_id)
        if task.status == TaskStatus.running:
            await self._try_succeed(session, task_id)

    # ------------------------------------------------------------------ plan
    async def _plan(self, session: AsyncSession, task_id: Any) -> list[TaskStep]:
        task = await session.get(Task, task_id)
        assert task is not None
        plan_prompt = _fmt_plan_prompt(task.instruction, task.agent)
        try:
            resp = await self.provider.complete(
                ChatRequest(
                    messages=[ChatMessage(role="user", content=plan_prompt)],
                    temperature=0.0,
                    max_tokens=1024,
                )
            )
            plan = self._parse_plan(resp.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Planning via provider failed (%s); using fallback plan.", exc)
            plan = [{"name": "respond", "tool": None, "kind": "respond", "params": {}}]

        steps: list[TaskStep] = []
        for i, raw in enumerate(plan):
            step = TaskStep(
                task_id=task.id,
                position=i,
                name=str(raw.get("name") or f"step-{i}"),
                tool=raw.get("tool"),
                status="pending",
                # Planned params are stored in `detail` until execution; the
                # execution result overwrites them with status detail.
                detail=json.dumps(raw.get("params") or {}, ensure_ascii=False),
            )
            session.add(step)
            steps.append(step)
        await session.flush()
        return steps

    @staticmethod
    def _parse_plan(content: str) -> list[dict[str, Any]]:
        text = content.strip()
        # Strip code fences if the model added them despite instructions.
        if text.startswith("```"):
            text = text.strip("`\n")
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("Plan has no steps.")
        cleaned: list[dict[str, Any]] = []
        for raw in steps:
            kind = str(raw.get("kind") or "respond")
            if kind not in ("mcp_tool", "respond"):
                kind = "respond"
            cleaned.append(
                {
                    "name": str(raw.get("name") or kind),
                    "tool": raw.get("tool"),
                    "kind": kind,
                    "params": raw.get("params") or {},
                }
            )
        return cleaned

    # ----------------------------------------------------------------- steps
    async def _execute_step(
        self,
        session: AsyncSession,
        task: Task,
        step: TaskStep,
        tool_outputs: list[dict[str, Any]],
    ) -> bool:
        """Execute one step. Returns True when the task paused for approval."""
        task.step_count += 1

        if step.tool is not None:
            kind = "mcp_tool"
        else:
            kind = "respond"
        # The plan's kind is not trusted on its own; derive from tool presence.
        if step.tool:
            kind = "mcp_tool"

        action = Action(
            kind=kind,
            tool=step.tool,
            resource=None,
            params=self._step_params(step),
        )
        verdict = self.policy.evaluate(action)

        await record_event(
            session,
            event_type="policy.decision",
            actor=task.agent,
            task_id=str(task.id),
            subject=step.tool or kind,
            outcome=verdict.decision.value,
            detail={"reason": verdict.reason},
        )

        if verdict.decision is Decision.DENY:
            raise PolicyDeniedError(f"Action denied by policy: {verdict.reason}")

        if verdict.decision is Decision.APPROVAL_REQUIRED:
            approval = await create_approval(
                session,
                task_id=task.id,
                step_id=step.id,
                action=action,
                reason=verdict.reason,
                requested_by=task.agent,
            )
            await record_event(
                session,
                event_type="approval.requested",
                actor=task.agent,
                task_id=str(task.id),
                subject=step.tool or kind,
                detail={"approval_id": str(approval.id), "reason": verdict.reason},
            )
            step.status = "pending"
            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.awaiting_approval)
            task.status = TaskStatus.awaiting_approval
            await session.commit()
            return True

        # Decision.ALLOW → execute now.
        if kind == "mcp_tool":
            await self._run_mcp_step(session, task, step, tool_outputs)
        else:
            await self._run_respond_step(session, task, step, tool_outputs)
        return False

    @staticmethod
    def _step_params(step: TaskStep) -> dict[str, Any]:
        # Params were produced during planning and stored in detail as JSON.
        if step.detail and step.detail.startswith("{"):
            try:
                return json.loads(step.detail)
            except ValueError:
                return {}
        return {}

    async def _run_mcp_step(
        self,
        session: AsyncSession,
        task: Task,
        step: TaskStep,
        tool_outputs: list[dict[str, Any]],
    ) -> None:
        from zuzu.integrations.mcp.registry import get_registry

        registry = get_registry()
        if registry is None or not registry.healthy:
            step.status = "failed"
            step.detail = "MCP tool server is unavailable; tool step cannot run."
            await record_event(
                session,
                event_type="tool.unavailable",
                actor=task.agent,
                task_id=str(task.id),
                subject=step.tool,
                outcome="error",
                detail={},
            )
            await self._fail(session, task, reason=step.detail)
            return

        params = self._step_params(step)
        try:
            result = await registry.invoke(str(step.tool), params)
        except Exception as exc:  # noqa: BLE001
            step.status = "failed"
            step.detail = f"Tool invocation failed: {exc}"[:500]
            await record_event(
                session,
                event_type="tool.invoked",
                actor=task.agent,
                task_id=str(task.id),
                subject=step.tool,
                outcome="error",
                detail={"error": type(exc).__name__},
            )
            await self._fail(session, task, reason=step.detail)
            return

        await record_event(
            session,
            event_type="tool.invoked",
            actor=task.agent,
            task_id=str(task.id),
            subject=step.tool,
            outcome="ok",
            detail={"result_chars": len(str(result))},
        )
        step.status = "succeeded"
        tool_outputs.append({"step": step.name, "tool": step.tool, "result": str(result)})

    async def _run_respond_step(
        self,
        session: AsyncSession,
        task: Task,
        step: TaskStep,
        tool_outputs: list[dict[str, Any]],
    ) -> None:
        context_lines = [f"- [{o['tool'] or o['step']}] {o['result'][:2000]}" for o in tool_outputs]
        prompt = task.instruction
        if context_lines:
            prompt += "\n\nCollected observations:\n" + "\n".join(context_lines)
        try:
            resp = await self.provider.complete(
                ChatRequest(
                    messages=[ChatMessage(role="user", content=prompt)],
                    max_tokens=2048,
                )
            )
        except ProviderError as exc:
            step.status = "failed"
            step.detail = exc.message
            await self._fail(session, task, reason=f"Provider failed: {exc.message}")
            return
        step.status = "succeeded"
        task.result = json.dumps({"summary": resp.content, "model": resp.model}, ensure_ascii=False)

    # -------------------------------------------------------------- lifecycle
    async def _try_succeed(self, session: AsyncSession, task_id: Any) -> None:
        task = await session.get(Task, task_id)
        assert task is not None
        steps = (
            (
                await session.execute(
                    select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.position)
                )
            )
            .scalars()
            .all()
        )
        pending = await session.execute(
            select(Approval).where(
                Approval.task_id == task_id,
                Approval.status == ApprovalStatus.pending,
            )
        )
        try:
            assert_can_succeed(
                step_statuses=[s.status for s in steps],
                pending_approvals=len(pending.scalars().all()),
            )
            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.succeeded)
            task.status = TaskStatus.succeeded
            task.finished_at = utcnow_naive()
            await record_event(
                session, event_type="task.succeeded", actor=task.agent, task_id=str(task.id)
            )
        except ConflictError as exc:
            await self._fail(session, task, reason=str(exc))
            return
        await session.commit()

    async def _fail(self, session: AsyncSession, task: Task, *, reason: str) -> None:
        if task.status in TERMINAL_STATES:
            return
        validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.failed)
        task.status = TaskStatus.failed
        task.failure_reason = reason[:2000]
        task.finished_at = utcnow_naive()
        await record_event(
            session,
            event_type="task.failed",
            actor=task.agent,
            task_id=str(task.id),
            outcome="error",
            detail={"reason": reason[:500]},
        )
        await session.commit()

    async def _check_deadline(self, task_id: Any, deadline: Any) -> None:
        if utcnow_naive() >= deadline:
            async with self.session_factory() as session:
                task = await session.get(Task, task_id)
                if task is not None and task.status not in TERMINAL_STATES:
                    await self._fail(
                        session,
                        task,
                        reason=f"Task timeout ({self.settings.task_timeout_seconds}s).",
                    )
            raise ConflictError(f"Task {task_id} exceeded its time budget.")

    # ------------------------------------------------------------------ resume
    async def resume_task(self, task_id: Any, approval_id: Any | None = None) -> None:
        """Continue a task paused in awaiting_approval after an approval decision.

        If the decided approval was approved, consumes it (single-use,
        fingerprint-checked) and continues executing the remaining planned
        steps. If it was rejected (or unusable), the task fails honestly.
        """
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task not found.")
            if task.status != TaskStatus.awaiting_approval:
                raise ConflictError(f"Task is not awaiting approval (status={task.status.value}).")

            if approval_id is None:
                # Fall back to the most recently decided approval for the task.
                stmt = (
                    select(Approval)
                    .where(Approval.task_id == task_id)
                    .where(Approval.status.in_([ApprovalStatus.approved, ApprovalStatus.rejected]))
                    .order_by(Approval.created_at.desc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row is None:
                    await self._fail(session, task, reason="No decided approval found.")
                    return
                approval_id = row.id
            await session.commit()

        # Resume executes in a fresh background task so the API call returns.
        _running[str(task_id)] = asyncio.create_task(self._resume_wrapper(task_id, approval_id))

    async def _resume_wrapper(self, task_id: Any, approval_id: Any) -> None:
        try:
            await self._resume(task_id, approval_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s resume crashed: %s", task_id, exc)
            async with self.session_factory() as session:
                task = await session.get(Task, task_id)
                if task is not None and task.status not in TERMINAL_STATES:
                    task.status = TaskStatus.failed
                    task.finished_at = utcnow_naive()
                    task.failure_reason = f"Internal error: {type(exc).__name__}"
                    await session.commit()

    async def _resume(self, task_id: Any, approval_id: Any) -> None:
        async with self.session_factory() as session:
            approval = await session.get(Approval, approval_id)
            assert approval is not None
            task = await session.get(Task, task_id)
            assert task is not None

            if approval.status == ApprovalStatus.rejected:
                await self._fail(
                    session,
                    task,
                    reason="The approval was rejected by the user.",
                )
                return
            if approval.status != ApprovalStatus.approved:
                # expired / already used etc.
                await self._fail(
                    session,
                    task,
                    reason=f"Approval is {approval.status.value}; task cannot continue.",
                )
                return

            # Single-use, fingerprint-checked consumption.
            try:
                await consume_approval(session, approval.id, action=action_from_approval(approval))
            except ConflictError as exc:
                await self._fail(session, task, reason=str(exc))
                return

            validate_transition(SMTaskStatus(task.status.value), SMTaskStatus.running)
            task.status = TaskStatus.running
            await record_event(
                session,
                event_type="approval.consumed",
                actor="user",
                task_id=str(task.id),
                subject=approval.action,
            )
            await session.commit()

        # Continue with the approved step and everything after it in the plan.
        deadline = utcnow_naive() + timedelta(seconds=self.settings.task_timeout_seconds)
        async with self.session_factory() as session:
            approval = await session.get(Approval, approval_id)
            assert approval is not None
            remaining: list[TaskStep] = []
            if approval.step_id:
                approved_step = await session.get(TaskStep, approval.step_id)
                if approved_step is None:  # pragma: no cover - data integrity guard
                    await self._fail(
                        session,
                        await self._fresh_task(session, task_id),
                        reason="Approved step row is missing.",
                    )
                    return
                stmt = (
                    select(TaskStep)
                    .where(TaskStep.task_id == task_id)
                    .where(TaskStep.position >= approved_step.position)
                    .order_by(TaskStep.position)
                )
                remaining = list((await session.execute(stmt)).scalars().all())
                # Reset the approved step back to pending before re-executing.
                if remaining and remaining[0].id == approved_step.id:
                    remaining[0].status = "pending"
                await session.commit()
            else:  # pragma: no cover - approvals always bind a tool step here
                await self._fail(
                    session,
                    await self._fresh_task(session, task_id),
                    reason="Approved step has no bound step row.",
                )
                return

            await self._execute_steps(session, task_id, remaining, deadline)


def is_running(task_id: Any) -> bool:
    t = _running.get(str(task_id))
    return t is not None and not t.done()
