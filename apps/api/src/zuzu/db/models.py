"""Zuzu ORM models.

Tables (v0.1.0):
- users
- conversations
- messages
- memories
- tasks
- task_steps
- approvals
- audit_events

Boundaries:
- messages    : conversation history (short-lived context, not durable knowledge)
- memories    : durable knowledge items, deletable by the user
- tasks       : orchestration records incl. steps and their status
- audit_events: append-only security-relevant event log (redacted)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from zuzu.db.base import Base, utcnow, uuid_fk, uuid_pk


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id")
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (Index("ix_conversations_user_created", "user_id", "created_at"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = uuid_fk("conversations.id")
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant|system|tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="fact")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (Index("ix_memories_user_created", "user_id", "created_at"),)


class TaskStatus(enum.StrEnum):
    queued = "queued"
    planning = "planning"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id")
    conversation_id: Mapped[uuid.UUID | None] = uuid_fk("conversations.id", nullable=True)
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False, length=32),
        nullable=False,
        default=TaskStatus.queued,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON string: {"summary": str, "model": str}
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    steps: Mapped[list[TaskStep]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskStep.position"
    )
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_tasks_user_status_created", "user_id", "status", "created_at"),)


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = uuid_fk("tasks.id")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending|running|succeeded|failed|skipped
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    task: Mapped[Task] = relationship(back_populates="steps")

    __table_args__ = (Index("ix_task_steps_task_position", "task_id", "position"),)


class ApprovalStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    used = "used"  # single-use: approval consumed by an execution


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = uuid_fk("tasks.id")
    step_id: Mapped[uuid.UUID | None] = uuid_fk("task_steps.id", nullable=True, index=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status", native_enum=False, length=32),
        nullable=False,
        default=ApprovalStatus.pending,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    # Full, exact request parameters; approvals are bound to this fingerprint.
    params: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    task: Mapped[Task] = relationship(back_populates="approvals")

    __table_args__ = (Index("ix_approvals_task_status", "task_id", "status"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    subject: Mapped[str | None] = mapped_column(String(256))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (Index("ix_audit_events_type_created", "event_type", "created_at"),)
