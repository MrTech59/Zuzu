"""Chat endpoints.

POST /api/v1/chat      — send a message, get the assistant reply (JSON or SSE).
POST /api/v1/chat/stream — convenience alias returning SSE.

Conversation history is stored in Postgres. The system prompt is constructed
server-side and never influenced by user-supplied content beyond the message
text itself (prompt-injection boundaries documented in docs/SECURITY.md).
"""

from __future__ import annotations

import json
import logging
import uuid as uuidlib
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from zuzu.ai.base import ChatMessage, ChatRequest
from zuzu.config import Settings, get_settings
from zuzu.db.engine import get_session
from zuzu.db.models import Conversation, Message
from zuzu.errors import NotFoundError, ProviderError, ValidationError
from zuzu.policy.system_prompt import build_system_prompt

logger = logging.getLogger("zuzu.api.chat")
router = APIRouter(prefix="/api/v1", tags=["chat"])

# v0.1.0 single-user deployment: all data belongs to the default user.
DEFAULT_USER_ID = uuidlib.UUID(int=0)  # resolved to a real row lazily


class ChatIn(BaseModel):
    conversation_id: uuidlib.UUID | None = None
    message: str = Field(min_length=1)
    stream: bool = False


class MessageOut(BaseModel):
    id: uuidlib.UUID
    role: str
    content: str
    model: str | None = None
    created_at: str


class ChatOut(BaseModel):
    conversation_id: uuidlib.UUID
    user_message: MessageOut
    assistant_message: MessageOut


class ConversationOut(BaseModel):
    id: uuidlib.UUID
    title: str | None
    created_at: str
    updated_at: str


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        model=m.model,
        created_at=m.created_at.isoformat() + "Z",
    )


async def _ensure_default_user(session) -> uuidlib.UUID:
    from zuzu.db.models import User

    user = await session.get(User, DEFAULT_USER_ID)
    if user is None:
        user = User(
            id=DEFAULT_USER_ID,
            username="local",
            display_name="Local user",
        )
        session.add(user)
        await session.flush()
    return user.id


async def _get_or_create_conversation(
    session, user_id: uuidlib.UUID, conversation_id: uuidlib.UUID | None, first_text: str
) -> Conversation:
    if conversation_id is not None:
        conv = await session.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError("Conversation not found.")
        return conv
    title = first_text.strip()[:80] or "New conversation"
    conv = Conversation(user_id=user_id, title=title)
    session.add(conv)
    await session.flush()
    return conv


async def _history(session, conversation_id: uuidlib.UUID, limit: int) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))


def _build_chat_request(history: list[Message], new_text: str, settings: Settings) -> ChatRequest:
    messages = [ChatMessage(role="system", content=build_system_prompt())]
    messages.extend(
        ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in history
        if m.role in ("user", "assistant")
    )
    messages.append(ChatMessage(role="user", content=new_text))
    return ChatRequest(messages=messages, max_tokens=2048)


async def _run_chat(session, body: ChatIn, settings: Settings) -> ChatOut:
    if len(body.message) > settings.chat_max_message_chars:
        limit = settings.chat_max_message_chars
        raise ValidationError(f"Message exceeds the maximum length of {limit} characters.")

    from zuzu.ai.factory import get_provider

    user_id = await _ensure_default_user(session)
    conv = await _get_or_create_conversation(session, user_id, body.conversation_id, body.message)

    user_msg = Message(conversation_id=conv.id, role="user", content=body.message)
    session.add(user_msg)
    await session.flush()

    history = await _history(session, conv.id, settings.chat_history_limit)
    history = [m for m in history if m.id != user_msg.id]

    provider = get_provider(settings)
    chat_request = _build_chat_request(history, body.message, settings)
    try:
        response = await provider.complete(chat_request)
    except ProviderError:
        # Persist nothing from the failed turn beyond the user message.
        raise

    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=response.content,
        provider=response.provider,
        model=response.model,
    )
    session.add(assistant_msg)
    await session.flush()

    return ChatOut(
        conversation_id=conv.id,
        user_message=_message_out(user_msg),
        assistant_message=_message_out(assistant_msg),
    )


async def _sse_stream(session, body: ChatIn, settings: Settings) -> AsyncIterator[bytes]:
    """Yield SSE events: meta, content deltas, then a final done/error event."""
    try:
        if len(body.message) > settings.chat_max_message_chars:
            limit = settings.chat_max_message_chars
            raise ValidationError(f"Message exceeds the maximum length of {limit} characters.")

        from zuzu.ai.factory import get_provider

        user_id = await _ensure_default_user(session)
        conv = await _get_or_create_conversation(
            session, user_id, body.conversation_id, body.message
        )

        user_msg = Message(conversation_id=conv.id, role="user", content=body.message)
        session.add(user_msg)
        await session.flush()

        history = await _history(session, conv.id, settings.chat_history_limit)
        history = [m for m in history if m.id != user_msg.id]

        provider = get_provider(settings)
        chat_request = _build_chat_request(history, body.message, settings)

        yield _sse(
            {
                "type": "meta",
                "conversation_id": str(conv.id),
                "model": body.message and (provider.name),
            }
        )

        full = []
        finish = None
        async for delta in provider.stream(chat_request):
            if delta.content:
                full.append(delta.content)
                yield _sse({"type": "delta", "content": delta.content})
            if delta.finish_reason:
                finish = delta.finish_reason

        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="".join(full),
            provider=provider.name,
            model=None,
        )
        session.add(assistant_msg)
        await session.commit()
        yield _sse(
            {
                "type": "done",
                "message_id": str(assistant_msg.id),
                "finish_reason": finish or "stop",
            }
        )
    except Exception as exc:  # noqa: BLE001 - streamed errors must reach the client
        logger.warning("Chat stream failed: %s: %s", type(exc).__name__, exc)
        code = getattr(exc, "code", "internal_error")
        yield _sse({"type": "error", "code": code, "message": str(exc)})
        try:
            await session.rollback()
        except Exception as rollback_error:  # pragma: no cover
            logger.debug("Rollback after stream error failed: %s", rollback_error)


def _sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


@router.post("/chat", response_model=ChatOut)
async def chat(
    body: ChatIn,
    request: Request,
    session=Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ChatOut:
    if body.stream:
        return StreamingResponse(  # type: ignore[return-value]
            _sse_stream(session, body, settings),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _run_chat(session, body, settings)


@router.get("/conversations")
async def list_conversations(session=Depends(get_session)) -> dict:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(200)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat() + "Z",
                "updated_at": c.updated_at.isoformat() + "Z",
            }
            for c in rows
        ]
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuidlib.UUID, session=Depends(get_session)) -> dict:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversation not found.")
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "id": str(conv.id),
        "title": conv.title,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "created_at": m.created_at.isoformat() + "Z",
            }
            for m in rows
        ],
    }
