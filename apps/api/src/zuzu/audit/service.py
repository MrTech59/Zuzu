"""Audit logging.

Audit events are append-only records of security-relevant actions: policy
decisions, approvals, tool invocations, task lifecycle changes and provider
errors. Payloads are redacted before storage (defense in depth) so secrets
never reach the database.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from zuzu.db.models import AuditEvent

logger = logging.getLogger("zuzu.audit")

# Keys whose values are dropped entirely from audit details.
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "token",
        "secret",
        "credentials",
        "nvidia_api_key",
        "zuzu_api_key",
        "cookie",
        "set-cookie",
    }
)

# Patterns that look like bearer tokens / long hex secrets even under other keys.
_BEARER_RE = None  # set lazily to avoid import cycle with logging module


def _import_bearer_re():
    global _BEARER_RE
    if _BEARER_RE is None:
        import re

        _BEARER_RE = re.compile(
            r"(?i)(\b(bearer|token|key|api[_-]?key|password|secret)\s*[:=]?\s*)([A-Za-z0-9_\-\.]{12,})"
        )
    return _BEARER_RE


def redact_value(value: Any, depth: int = 0) -> Any:
    """Recursively redact secrets from a JSON-like value."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key_l = str(k).lower()
            if key_l in _SENSITIVE_KEYS or any(
                s in key_l
                for s in ("api_key", "password", "secret", "token", "authorization", "credential")
            ):
                out[str(k)] = "***REDACTED***"
            else:
                out[str(k)] = redact_value(v, depth + 1)
        return out
    if isinstance(value, list):
        return [redact_value(v, depth + 1) for v in value]
    if isinstance(value, str):
        bearer_re = _import_bearer_re()
        return bearer_re.sub(r"\1***REDACTED***", value)
    return value


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor: str,
    outcome: str = "ok",
    task_id: str | None = None,
    subject: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist an audit event with redacted detail. Never raises to the caller."""
    try:
        import uuid as uuidlib

        redacted = redact_value(detail or {})
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            outcome=outcome,
            task_id=uuidlib.UUID(task_id) if isinstance(task_id, str) else task_id,
            subject=subject,
            detail=json.dumps(redacted, ensure_ascii=False, default=str),
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(event)
        await session.flush()
        return event
    except Exception:
        # Audit failures must not break the primary operation, but must be loud.
        logger.exception("Failed to persist audit event %s", event_type)
        raise


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
