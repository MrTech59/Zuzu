"""AI provider factory.

Chooses between the real NVIDIA provider and the deterministic mock based on
settings (AI_PROVIDER) and credential availability. Never logs or exposes the
API key.
"""

from __future__ import annotations

import logging
import threading

from zuzu.ai.base import ChatProvider
from zuzu.config import Settings

logger = logging.getLogger("zuzu.ai.factory")

_lock = threading.Lock()
_provider: ChatProvider | None = None


def build_provider(settings: Settings) -> ChatProvider:
    """Construct a provider per configuration. Raises ProviderError on bad config."""
    if settings.ai_provider == "mock":
        from zuzu.ai.mock import MockProvider

        return MockProvider()

    if not settings.nvidia_api_key:
        raise ValueError(
            "AI_PROVIDER is 'nvidia' but NVIDIA_API_KEY is not set. Set the key or "
            "configure AI_PROVIDER=mock for offline use."
        )

    from zuzu.ai.nvidia import NvidiaProvider

    return NvidiaProvider(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        default_model=settings.resolved_nvidia_model,
        timeout_seconds=settings.nvidia_timeout_seconds,
        connect_timeout_seconds=settings.nvidia_connect_timeout_seconds,
        max_retries=settings.nvidia_max_retries,
    )


def get_provider(settings: Settings | None = None) -> ChatProvider:
    """Process-wide provider instance (idempotent)."""
    global _provider
    with _lock:
        if _provider is None:
            _provider = build_provider(settings or get_settings_cached())
        return _provider


def reset_provider() -> None:
    """Drop the cached provider (used by tests and config reloads)."""
    global _provider
    with _lock:
        _provider = None


def get_settings_cached() -> Settings:
    from zuzu.config import get_settings

    return get_settings()
