"""Zuzu's own MCP client (Streamable HTTP transport).

The transport was verified against the live server (picoclaw-browser v1.30.0):
- Endpoint: POST {server_url}/mcp
- initialize → 200 with `mcp-session-id` header; notifications/initialized → 202
- tools/call over the same session id

This module wraps the official `mcp` SDK's streamable HTTP client. It is the
only place Zuzu speaks MCP; the rest of the app depends on the registry
interface. The server treats tool output as untrusted data (see SECURITY.md).

Connection model: the SDK exposes context managers, so a long-lived
connection is held inside a dedicated asyncio task and torn down on stop().
Reconnection is bounded (bounded retries) and failures are surfaced via
`healthy` and `last_error`; the application must keep working without MCP.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import jsonschema

logger = logging.getLogger("zuzu.mcp")

MCP_ENDPOINT_PATH = "/mcp"


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


class McpClientError(Exception):
    """MCP client-level failure (transport, protocol, timeout)."""


class ToolValidationError(McpClientError):
    pass


class McpClient:
    """MCP client over Streamable HTTP using the official SDK."""

    def __init__(
        self,
        *,
        server_url: str,
        connect_timeout: float = 10.0,
        request_timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.tools: dict[str, ToolSpec] = {}
        self.server_info: dict[str, Any] = {}
        self.last_error: str | None = None
        self._session: Any = None
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()

    # -------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Open the connection, initialize and discover tools."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=self.connect_timeout + 15.0)
        except TimeoutError as exc:
            raise McpClientError(
                f"MCP connection did not initialize within {self.connect_timeout + 15.0:.0f}s"
            ) from exc

        if self._session is None:
            raise McpClientError(self.last_error or "MCP connection failed.")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: S110 - best effort
                pass
            self._task = None
        self._session = None
        self._ready.clear()

    async def _run(self) -> None:
        """Hold the MCP connection open until stop()."""
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = self.server_url
        if not url.endswith(MCP_ENDPOINT_PATH):
            url = url + MCP_ENDPOINT_PATH

        try:
            async with streamablehttp_client(url, timeout=self.request_timeout) as (
                read_stream,
                write_stream,
                _get_session_id,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    init_result = await asyncio.wait_for(
                        session.initialize(), timeout=self.connect_timeout
                    )
                    self.server_info = {
                        "name": getattr(getattr(init_result, "serverInfo", None), "name", None),
                        "version": getattr(
                            getattr(init_result, "serverInfo", None), "version", None
                        ),
                        "protocol": getattr(init_result, "protocolVersion", None),
                    }
                    self._session = session
                    await self._discover_tools(session)
                    self.last_error = None
                    self._ready.set()
                    # Keep the connection open; wake on stop.
                    await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"MCP connection failed: {type(exc).__name__}"
            logger.warning("MCP connection task ended: %s", self.last_error)
        finally:
            self._session = None
            self._ready.set()  # unblock start() waiters on failure

    async def _discover_tools(self, session: Any) -> None:
        result = await asyncio.wait_for(session.list_tools(), timeout=self.request_timeout)
        discovered: dict[str, ToolSpec] = {}
        for tool in getattr(result, "tools", []):
            discovered[tool.name] = ToolSpec(
                name=tool.name,
                description=getattr(tool, "description", "") or "",
                input_schema=getattr(tool, "inputSchema", None) or {},
            )
        self.tools = discovered
        logger.info("MCP tool discovery complete: %d tools", len(discovered))

    # ------------------------------------------------------------ properties
    @property
    def healthy(self) -> bool:
        return self._session is not None and self.last_error is None

    def list_tools(self) -> list[ToolSpec]:
        return list(self.tools.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self.tools.get(name)

    # ------------------------------------------------------------- invocation
    def validate_arguments(self, tool: str, arguments: dict[str, Any]) -> None:
        """Validate arguments against the discovered tool schema."""
        spec = self.get_tool(tool)
        if spec is None:
            raise ToolValidationError(f"Unknown tool: {tool}")
        schema = spec.input_schema or {}
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ToolValidationError(
                f"Arguments for tool '{tool}' failed schema validation: {exc.message}"
            ) from exc

    async def invoke(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Invoke an approved tool with bounded retries and timeout.

        Raises:
            ToolValidationError: unknown tool or schema-invalid arguments.
            McpClientError: transport failure, timeout or protocol error.
        """
        self.validate_arguments(tool, arguments)
        if self._session is None:
            raise McpClientError("MCP client is not connected.")

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(tool, arguments or {}),
                    timeout=self.request_timeout,
                )
                return _extract_result(result)
            except TimeoutError:
                last_exc = McpClientError(
                    f"MCP tool '{tool}' timed out after {self.request_timeout}s"
                )
                logger.warning("MCP tool timeout (attempt %d): %s", attempt, tool)
            except ToolValidationError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = McpClientError(
                    f"MCP tool '{tool}' invocation failed: {type(exc).__name__}"
                )
                logger.warning(
                    "MCP tool failure (attempt %d): %s: %s", attempt, tool, type(exc).__name__
                )
            await asyncio.sleep(min(0.25 * attempt, 1.0))

        raise last_exc or McpClientError(f"MCP tool '{tool}' failed.")

    async def healthcheck(self) -> bool:
        if self._session is None:
            return False
        try:
            await asyncio.wait_for(self._session.send_ping(), timeout=5.0)
            return True
        except Exception:  # noqa: BLE001
            return False


def _extract_result(result: Any) -> Any:
    """Extract a serializable payload from a CallToolResult."""
    if getattr(result, "isError", False):
        texts = [c.text for c in getattr(result, "content", []) if getattr(c, "text", None)]
        raise McpClientError(f"Tool returned an error: {'; '.join(texts)[:500]}")
    if hasattr(result, "structuredContent") and result.structuredContent:
        return result.structuredContent
    texts = [c.text for c in getattr(result, "content", []) if getattr(c, "text", None)]
    if texts:
        return "\n".join(texts)
    return ""


def started_at_monotonic() -> float:
    return time.monotonic()
