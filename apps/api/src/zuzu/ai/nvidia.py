"""NVIDIA cloud AI adapter (OpenAI-compatible endpoint).

Contract (verified against NVIDIA documentation, 2026-10):
- Base URL: https://integrate.api.nvidia.com/v1 (configurable)
- POST {base}/chat/completions with OpenAI-style payload, Bearer auth.
- Streaming uses SSE with `data: {...}` chunks and a terminating `data: [DONE]`.

Robustness requirements implemented here:
- Bounded connect + total timeouts, bounded retries (idempotent single-shot calls).
- Clear ProviderError subclasses for auth failures, rate limits, outages,
  timeouts and malformed responses.
- API key never appears in logs or exception messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from zuzu.ai.base import ChatProvider, ChatRequest, ChatResponse, StreamDelta
from zuzu.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
)

logger = logging.getLogger("zuzu.ai.nvidia")


class NvidiaProvider(ChatProvider):
    """OpenAI-compatible adapter for the NVIDIA integrate API."""

    name = "nvidia"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        default_model: str = "meta/llama-3.3-70b-instruct",
        timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError(
                "NVIDIA_API_KEY is not configured. Set it in the environment or "
                "select the mock provider for offline development."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.max_retries = max_retries
        self._client = client
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=self.connect_timeout_seconds),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ errors
    @staticmethod
    def _map_status(status_code: int, body_text: str) -> ProviderError:
        # Keep the response snippet short; provider error bodies are untrusted
        # and are surfaced only as detail, never as a raised exception message.
        snippet = body_text[:300]
        if status_code in (401, 403):
            return ProviderAuthError(
                "The AI provider rejected the configured credentials "
                f"(HTTP {status_code}). Check NVIDIA_API_KEY."
            )
        if status_code == 429:
            return ProviderError(
                "The AI provider rate limit was hit (HTTP 429). Retry later.",
                detail={"http_status": 429},
            )
        if status_code >= 500:
            return ProviderError(
                f"The AI provider returned a server error (HTTP {status_code}).",
                detail={"http_status": status_code},
            )
        return ProviderError(
            f"The AI provider rejected the request (HTTP {status_code}).",
            detail={"http_status": status_code, "response": snippet},
        )

    # ---------------------------------------------------------------- complete
    async def complete(self, request: ChatRequest) -> ChatResponse:
        model = request.model or self.default_model
        payload = self._build_payload(request, model, stream=False)
        client = await self._get_client()
        attempt = 0
        last_error: ProviderError | None = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(
                        self.timeout_seconds, connect=self.connect_timeout_seconds
                    ),
                )
            except httpx.TimeoutException as exc:
                last_error = ProviderTimeoutError(
                    "The AI provider timed out.", detail={"timeout_s": self.timeout_seconds}
                )
                logger.warning(
                    "NVIDIA request timed out (attempt %d): %s", attempt, type(exc).__name__
                )
                continue
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    "Could not reach the AI provider.", detail={"error": type(exc).__name__}
                )
                logger.warning(
                    "NVIDIA request failed (attempt %d): %s", attempt, type(exc).__name__
                )
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return self._parse_completion(data, model)
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    raise ProviderError(
                        "The AI provider returned an invalid response.",
                        detail={"parse_error": type(exc).__name__},
                    ) from exc

            error = self._map_status(resp.status_code, resp.text)
            # Only retry transient failures; auth/validation errors are fatal.
            if resp.status_code in (429,) or resp.status_code >= 500:
                last_error = error
                await asyncio.sleep(min(0.5 * attempt, 2.0))
                continue
            raise error

        raise last_error or ProviderError("The AI provider request failed.")

    # ------------------------------------------------------------------ stream
    async def _stream(self, request: ChatRequest) -> AsyncIterator[StreamDelta]:
        model = request.model or self.default_model
        payload = self._build_payload(request, model, stream=True)
        client = await self._get_client()
        try:
            req = client.build_request(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={**self._headers(), "Accept": "text/event-stream"},
                timeout=httpx.Timeout(self.timeout_seconds, connect=self.connect_timeout_seconds),
            )
            resp = await client.send(req, stream=True)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The AI provider timed out during streaming.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach the AI provider for streaming.",
                detail={"error": type(exc).__name__},
            ) from exc

        if resp.status_code != 200:
            body = (await resp.aread()).decode("utf-8", "replace")
            raise self._map_status(resp.status_code, body)

        try:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except ValueError:
                    logger.warning("Skipping malformed SSE chunk from provider")
                    continue
                delta, finish = self._parse_stream_chunk(chunk, model)
                if delta:
                    yield StreamDelta(content=delta, finish_reason=finish)
                elif finish:
                    yield StreamDelta(content="", finish_reason=finish)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The AI provider timed out mid-stream.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "The AI provider stream failed.", detail={"error": type(exc).__name__}
            ) from exc
        finally:
            await resp.aclose()

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamDelta]:
        return self._stream(request)

    # ------------------------------------------------------------------- parse
    @staticmethod
    def _build_payload(request: ChatRequest, model: str, *, stream: bool) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

    @staticmethod
    def _parse_completion(data: dict[str, Any], model: str) -> ChatResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("The AI provider response had no choices.")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderError("The AI provider response had no message content.")
        usage_raw = data.get("usage") or {}
        usage = {k: int(v) for k, v in usage_raw.items() if isinstance(v, int)}
        return ChatResponse(
            content=content,
            model=str(data.get("model") or model),
            provider="nvidia",
            finish_reason=choice.get("finish_reason"),
            usage=usage,
        )

    @staticmethod
    def _parse_stream_chunk(chunk: dict[str, Any], model: str) -> tuple[str | None, str | None]:
        choices = chunk.get("choices") or []
        if not choices:
            return None, None
        choice = choices[0]
        delta = choice.get("delta") or {}
        content = delta.get("content")
        finish = choice.get("finish_reason")
        if isinstance(content, str) and content:
            return content, finish
        return None, finish

    # ------------------------------------------------------------- healthcheck
    async def healthcheck(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            return resp.status_code == 200
        except Exception:
            return False
