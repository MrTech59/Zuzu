"""Application-level MCP registry.

Owns the connection lifecycle and exposes a stable, policy-checked surface:

    registry.invoke(tool, params)

The registry itself enforces schema validation. Permission decisions are made
by the policy engine in backend code (the runner) before invoke() is reached —
MCP tools are capabilities, never automatic permission grants.

The application must work when MCP is unreachable: `get_registry()` returns
None when disabled/unavailable, and callers degrade gracefully.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from zuzu.config import get_settings

logger = logging.getLogger("zuzu.mcp.registry")

_registry: McpRegistry | None = None
_lock = threading.Lock()


def _tool_to_dict(t: Any) -> dict:
    """Normalize a ToolSpec object or dict into the registry's dict shape."""
    if isinstance(t, dict):
        return {
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "input_schema": t.get("input_schema") or {},
        }
    return {
        "name": getattr(t, "name", ""),
        "description": getattr(t, "description", "") or "",
        "input_schema": getattr(t, "input_schema", None) or {},
    }


class McpRegistry:
    """Registry facade over McpClient with health tracking."""

    def __init__(self, client: Any) -> None:  # client: McpClient-like
        self._client = client
        self.started_at: float | None = None

    async def start(self) -> None:
        import time as _time

        await self._client.start()
        self.started_at = _time.monotonic()

    async def stop(self) -> None:
        await self._client.stop()

    @property
    def healthy(self) -> bool:
        try:
            return self._client.healthy
        except Exception:  # noqa: BLE001
            return False

    def list_tools(self) -> list[dict]:
        return [_tool_to_dict(t) for t in self._client.list_tools()]

    def get_tool(self, name: str) -> dict | None:
        t = self._client.get_tool(name)
        return _tool_to_dict(t) if t is not None else None

    async def invoke(self, tool: str, params: dict) -> Any:
        """Invoke an approved tool. Schema validation happens here too."""
        return await self._client.invoke(tool, params)

    async def healthcheck(self) -> bool:
        return await self._client.healthcheck()


async def init_registry() -> McpRegistry | None:
    """Create and start the registry from settings. Returns None when disabled."""
    global _registry
    settings = get_settings()
    if not settings.mcp_enabled:
        logger.info("MCP integration disabled by configuration.")
        return None

    transport = settings.mcp_transport or "streamable-http"
    if transport != "streamable-http":
        logger.error("Unsupported MCP transport %r; disabling MCP.", transport)
        return None
    if not settings.mcp_server_url:
        logger.error("ZUZU_MCP_SERVER_URL is empty; disabling MCP.")
        return None

    with _lock:
        if _registry is None:
            from zuzu.integrations.mcp.client import McpClient

            client = McpClient(
                server_url=settings.mcp_server_url,
                connect_timeout=settings.mcp_connect_timeout_seconds,
                request_timeout=settings.mcp_request_timeout_seconds,
            )
            _registry = McpRegistry(client)
    try:
        await _registry.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP registry failed to start: %s — continuing without MCP.", exc)
        global_disable()
        return None
    logger.info("MCP registry started (%s tools available).", len(_registry.list_tools()))
    return _registry


def global_disable() -> None:
    """Disable MCP for the process lifetime (used on hard failures)."""
    global _registry
    with _lock:
        _registry = None


def get_registry() -> McpRegistry | None:
    return _registry


def set_registry(registry: McpRegistry | None) -> None:
    """Install a registry explicitly (used by tests to inject mocks)."""
    global _registry
    with _lock:
        _registry = registry


async def shutdown_registry() -> None:
    global _registry
    with _lock:
        reg = _registry
        _registry = None
    if reg is not None:
        try:
            await reg.stop()
        except Exception:  # noqa: S110 - best effort on shutdown
            pass
