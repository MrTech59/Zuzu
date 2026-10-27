"""NVIDIA adapter tests using httpx.MockTransport — no real credentials."""

from __future__ import annotations

import json

import httpx
import pytest

from zuzu.ai.base import ChatMessage, ChatRequest
from zuzu.ai.nvidia import NvidiaProvider
from zuzu.errors import ProviderAuthError, ProviderError

KEY = "nvapi-test-key-not-real"


def make_provider(handler) -> NvidiaProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return NvidiaProvider(
        api_key=KEY,
        base_url="https://integrate.api.nvidia.com/v1",
        client=client,
        max_retries=1,
    )


def completion_body(content: str, model: str = "test-model") -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
    }


@pytest.mark.asyncio
async def test_complete_success() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=completion_body("hello"))

    provider = make_provider(handler)
    resp = await provider.complete(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert resp.content == "hello"
    assert resp.model == "test-model"
    assert resp.provider == "nvidia"
    assert seen["url"].startswith("https://integrate.api.nvidia.com/v1/chat/completions")
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["payload"]["model"] == "meta/llama-3.3-70b-instruct"


@pytest.mark.asyncio
async def test_auth_error_is_not_retried_and_not_echoed() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "invalid key"})

    provider = make_provider(handler)
    with pytest.raises(ProviderAuthError) as exc:
        await provider.complete(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert calls["n"] == 1  # no retry on auth failures
    # The raised message must not contain the API key.
    assert KEY not in str(exc.value)


@pytest.mark.asyncio
async def test_rate_limit_retries_then_fails() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"detail": "rate limited"})

    provider = make_provider(handler)
    with pytest.raises(ProviderError) as exc:
        await provider.complete(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert calls["n"] == 2  # initial + 1 retry
    assert exc.value.code == "provider_error"


@pytest.mark.asyncio
async def test_server_error_returns_clear_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    provider = make_provider(handler)
    with pytest.raises(ProviderError):
        await provider.complete(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))


@pytest.mark.asyncio
async def test_invalid_response_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = make_provider(handler)
    with pytest.raises(ProviderError):
        await provider.complete(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))


@pytest.mark.asyncio
async def test_streaming_sse_chunks() -> None:
    sse_body = (
        'data: {"id":"1","choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"id":"1","choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"id":"1","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_provider(handler)
    chunks = []
    async for delta in provider.stream(
        ChatRequest(messages=[ChatMessage(role="user", content="hi")], stream=True)
    ):
        chunks.append(delta)
    assert "".join(c.content for c in chunks) == "Hello"
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_missing_api_key_rejected() -> None:
    with pytest.raises(ProviderError):
        NvidiaProvider(api_key="")


@pytest.mark.asyncio
async def test_mock_provider_deterministic_and_uses_agent_system_prompt() -> None:
    from zuzu.ai.mock import MockProvider

    p = MockProvider()
    resp = await p.complete(
        ChatRequest(
            messages=[
                ChatMessage(
                    role="system", content="system prompt mentioning agent name: researcher"
                ),
                ChatMessage(role="user", content="What is 2+2?"),
            ]
        )
    )
    assert "[agent=researcher]" in resp.content

    err = MockProvider()
    with pytest.raises(ProviderError):
        await err.complete(
            ChatRequest(messages=[ChatMessage(role="user", content="FAKE_ERROR:nope")])
        )
