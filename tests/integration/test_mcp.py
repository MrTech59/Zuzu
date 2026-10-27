"""MCP integration tests using the mock registry (offline)."""

from __future__ import annotations

import pytest

from zuzu.integrations.mcp.client import McpClientError, ToolValidationError
from zuzu.integrations.mcp.mock import MockMcpRegistry


@pytest.mark.asyncio
async def test_mock_registry_lists_browser_tools() -> None:
    reg = MockMcpRegistry()
    await reg.start()
    tools = reg.list_tools()
    names = {t["name"] for t in tools}
    assert "browser_navigate" in names
    assert "browser_read" in names
    await reg.stop()


@pytest.mark.asyncio
async def test_tool_argument_schema_validation() -> None:
    reg = MockMcpRegistry()
    await reg.start()

    # Valid arguments pass.
    await reg.invoke("browser_navigate", {"url": "https://example.com"})
    assert reg.calls[-1] == ("browser_navigate", {"url": "https://example.com"})

    # Missing required argument fails validation.
    with pytest.raises(ToolValidationError):
        await reg.invoke("browser_navigate", {})

    # Wrong type fails validation.
    with pytest.raises(ToolValidationError):
        await reg.invoke("browser_navigate", {"url": 123})

    # Unknown tool fails.
    with pytest.raises(ToolValidationError):
        await reg.invoke("browser_totally_fake", {})

    await reg.stop()


@pytest.mark.asyncio
async def test_unavailable_registry_raises_clear_error() -> None:
    reg = MockMcpRegistry(healthy=False)
    with pytest.raises(McpClientError):
        await reg.start()


@pytest.mark.asyncio
async def test_invoke_on_disconnected_registry() -> None:
    reg = MockMcpRegistry()
    await reg.start()
    await reg.stop()
    with pytest.raises(McpClientError, match="not connected"):
        await reg.invoke("browser_read", {})


@pytest.mark.asyncio
async def test_failing_tool_reports_error() -> None:
    reg = MockMcpRegistry(fail_tools={"browser_read"})
    await reg.start()
    with pytest.raises(McpClientError, match="error"):
        await reg.invoke("browser_read", {})
    await reg.stop()


@pytest.mark.asyncio
async def test_mcp_client_argument_validation_offline() -> None:
    """McpClient.validate_arguments works without a live connection."""
    from zuzu.integrations.mcp.client import McpClient

    client = McpClient(server_url="http://localhost:1")  # not connected
    client.tools = {
        "browser_navigate": type(
            "T",
            (),
            {
                "name": "browser_navigate",
                "description": "",
                "input_schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        )()
    }
    client.validate_arguments("browser_navigate", {"url": "https://x.com"})
    with pytest.raises(ToolValidationError):
        client.validate_arguments("browser_navigate", {})
    with pytest.raises(ToolValidationError):
        client.validate_arguments("missing_tool", {})


@pytest.mark.asyncio
async def test_registry_adapter_surface(monkeypatch) -> None:
    """McpRegistry facade exposes the same behaviour as the client."""
    from zuzu.integrations.mcp.mock import MockMcpRegistry
    from zuzu.integrations.mcp.registry import McpRegistry

    reg = McpRegistry(MockMcpRegistry())
    await reg.start()
    assert reg.healthy
    tools = reg.list_tools()
    assert any(t["name"] == "browser_navigate" for t in tools)
    assert reg.get_tool("browser_read") is not None
    assert reg.get_tool("nope") is None
    result = await reg.invoke("browser_current", {})
    assert "Mock Page" in str(result)
    await reg.stop()
    assert not reg.healthy
