"""Declarative base and shared column helpers.

Conventions:
- UUID primary keys (native UUID on Postgres, CHAR(36) elsewhere via
  SQLAlchemy's portable Uuid type).
- UTC timestamps only (naive UTC via the utcnow helper).
- Foreign keys with explicit ondelete behaviour.
- No secrets stored in message, memory or audit payloads (enforced by the
  audit redaction service and reviewed at call sites).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp (DB-agnostic, always UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    """Zuzu declarative base."""


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)


def uuid_fk(
    target: str, *, ondelete: str = "CASCADE", index: bool = True, nullable: bool = False
) -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


def str_col(length: int | None = None, **kw: Any) -> Mapped[str]:
    return mapped_column(String(length) if length else String(), **kw)
