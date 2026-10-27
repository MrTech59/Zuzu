"""Chat endpoint tests (mock provider)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_chat_roundtrip_persists_history(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "echo:Zuzu speaks"},
    )
    assert resp.status_code == 200
    body = resp.json()
    conv_id = body["conversation_id"]
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["content"].endswith("Zuzu speaks")

    # History persists.
    hist = await client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert hist.status_code == 200
    roles = [m["role"] for m in hist.json()["messages"]]
    assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_chat_second_turn_reuses_conversation(
    client: httpx.AsyncClient, auth_headers
) -> None:
    first = await client.post("/api/v1/chat", headers=auth_headers, json={"message": "echo:one"})
    conv_id = first.json()["conversation_id"]
    second = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "echo:two", "conversation_id": conv_id},
    )
    assert second.json()["conversation_id"] == conv_id


@pytest.mark.asyncio
async def test_chat_streaming_sse(client: httpx.AsyncClient, auth_headers) -> None:
    async with client.stream(
        "POST",
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "echo:stream me", "stream": True},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events: list[dict] = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                import json

                events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    content = "".join(e["content"] for e in events if e["type"] == "delta")
    assert content.endswith("stream me")


@pytest.mark.asyncio
async def test_chat_unknown_conversation_404(client: httpx.AsyncClient, auth_headers) -> None:
    import uuid as uuidlib

    resp = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "hi", "conversation_id": str(uuidlib.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_empty_message_422(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post("/api/v1/chat", headers=auth_headers, json={"message": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_error_stream_returns_error_event(
    client: httpx.AsyncClient, auth_headers, monkeypatch
) -> None:
    """Provider failure during streaming yields an SSE error event, not silence."""
    from zuzu.ai import factory as ai_factory
    from zuzu.ai.mock import MockProvider

    class FailingProvider(MockProvider):
        async def complete(self, request):
            from zuzu.errors import ProviderError

            raise ProviderError("Provider is down (mock).")

    monkeypatch.setattr(ai_factory, "get_provider", lambda settings=None: FailingProvider())
    # Reset the cached provider so the failing one is used.

    async with client.stream(
        "POST",
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "echo:x", "stream": True},
    ) as resp:
        assert resp.status_code == 200
        events: list[dict] = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                import json

                events.append(json.loads(line[6:]))
    assert any(e["type"] == "error" for e in events)
