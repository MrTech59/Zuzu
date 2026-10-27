"""Mock MCP registry for offline development and tests.

Implements the same surface as McpRegistry with canned, deterministic
behaviour so MCP-dependent code paths (orchestration, policy, argument
validation) are fully testable without the live server.
"""

from __future__ import annotations

from typing import Any

from zuzu.integrations.mcp.client import McpClientError, ToolValidationError

MOCK_TOOLS: dict[str, dict[str, Any]] = {
    "browser_navigate": {
        "name": "browser_navigate",
        "description": "Navigate the current browser tab to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "title": "Url"}},
            "required": ["url"],
            "title": "browser_navigateArguments",
        },
    },
    "browser_read": {
        "name": "browser_read",
        "description": "Read visible text from the current webpage.",
        "input_schema": {"type": "object", "properties": {}, "title": "browser_readArguments"},
    },
    "browser_current": {
        "name": "browser_current",
        "description": "Return the current page title and URL.",
        "input_schema": {"type": "object", "properties": {}, "title": "browser_currentArguments"},
    },
    "browser_tabs": {
        "name": "browser_tabs",
        "description": "List all open browser tabs.",
        "input_schema": {"type": "object", "properties": {}, "title": "browser_tabsArguments"},
    },
}


class MockMcpRegistry:
    """Deterministic mock implementing the McpRegistry surface."""

    def __init__(self, *, healthy: bool = True, fail_tools: set[str] | None = None) -> None:
        self._healthy = healthy
        self.fail_tools = fail_tools or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.started_at = 0.0
        self._current_page = "about:blank"

    # lifecycle ------------------------------------------------------------
    async def start(self) -> None:
        if not self._healthy:
            raise McpClientError("Mock MCP server is offline.")

    async def stop(self) -> None:
        self._healthy = False

    # introspection ---------------------------------------------------------
    @property
    def healthy(self) -> bool:
        return self._healthy

    def list_tools(self) -> list[dict[str, Any]]:
        return [dict(t) for t in MOCK_TOOLS.values()]

    def get_tool(self, name: str) -> dict[str, Any] | None:
        t = MOCK_TOOLS.get(name)
        return dict(t) if t else None

    # invocation -------------------------------------------------------------
    def validate_arguments(self, tool: str, arguments: dict[str, Any]) -> None:
        import jsonschema

        spec = MOCK_TOOLS.get(tool)
        if spec is None:
            raise ToolValidationError(f"Unknown tool: {tool}")
        try:
            jsonschema.validate(instance=arguments, schema=spec["input_schema"])
        except jsonschema.ValidationError as exc:
            raise ToolValidationError(
                f"Arguments for tool '{tool}' failed schema validation: {exc.message}"
            ) from exc

    async def invoke(self, tool: str, params: dict[str, Any]) -> Any:
        if not self._healthy:
            raise McpClientError("MCP client is not connected.")
        self.validate_arguments(tool, params)
        self.calls.append((tool, dict(params)))
        if tool in self.fail_tools:
            raise McpClientError(f"Tool returned an error: mock failure for {tool}")
        if tool == "browser_navigate":
            self._current_page = params["url"]
            return {"result": f"Navigation complete: {params['url']}"}
        if tool == "browser_current":
            return {"result": f"TITLE: Mock Page\nURL: {self._current_page}"}
        if tool == "browser_read":
            return {"result": "Mock page text content."}
        if tool == "browser_tabs":
            return {"result": "Tab 1: Mock Page"}
        return {"result": f"mock result for {tool}"}

    async def healthcheck(self) -> bool:
        return self._healthy
