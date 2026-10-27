"""AI provider abstraction.

Zuzu talks to cloud LLMs through this narrow protocol only. The NVIDIA adapter
is one implementation; the mock provider enables offline development and the
test suite without credentials.

The provider layer must:
- Report failures as ProviderError subclasses (never pretend success).
- Redact secrets from any raised/logged content.
- Enforce bounded timeouts and retries.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(slots=True)
class ChatRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False


@dataclass(slots=True)
class ChatResponse:
    content: str
    model: str
    provider: str
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class StreamDelta:
    """One incremental chunk of a streamed completion."""

    content: str
    finish_reason: str | None = None


class ChatProvider(abc.ABC):
    """Protocol every AI provider implements."""

    name: str = "base"

    @abc.abstractmethod
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Single-shot completion. Raises ProviderError subclasses on failure."""

    @abc.abstractmethod
    def stream(self, request: ChatRequest) -> AsyncIterator[StreamDelta]:
        """Streaming completion. Raises ProviderError subclasses on failure."""

    @abc.abstractmethod
    async def healthcheck(self) -> bool:
        """Cheap connectivity check; never raises."""
