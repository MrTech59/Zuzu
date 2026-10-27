"""Live MCP approved-tool verification script.

Performs a full MCP handshake against the configured server, discovers the
actual tool schemas, validates the target tool's input schema, records an
explicit approval decision, and invokes the tool through Zuzu's own McpClient.

Only state-changing MCP tools that require approval under Zuzu's policy are
accepted. Read-only tools should be verified with scripts/verify_mcp.py.

Usage:
    python scripts/verify_mcp_approved.py --tool browser_navigate \\
        --target-url http://example.com --yes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from zuzu.integrations.mcp.client import McpClient
from zuzu.policy.engine import Action, Decision, load_policy_from_files

# Tools that Zuzu's default policy treats as state-changing and approval-required.
STATE_CHANGING_TOOLS = {
    "browser_navigate",
    "browser_new_tab",
    "browser_switch_tab",
    "browser_back",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_select",
    "browser_scroll",
    "browser_screenshot",
    "browser_download",
}


def build_arguments(tool: str, target_url: str | None) -> dict:
    """Build minimal, schema-valid arguments for a supported tool."""
    if tool == "browser_navigate":
        return {"url": target_url or "http://example.com"}
    if tool in {"browser_new_tab", "browser_back"}:
        return {}
    if tool == "browser_switch_tab":
        return {"page_id": 0}
    if tool == "browser_click":
        return {"selector": "body"}
    if tool in {"browser_type", "browser_press"}:
        return {"selector": "body", "text": "approved test"}
    if tool == "browser_select":
        return {"selector": "select", "value": "approved"}
    if tool == "browser_scroll":
        return {"direction": "down"}
    if tool == "browser_screenshot":
        return {"path": "zuzu-approved-test.png"}
    if tool == "browser_download":
        return {"url": target_url or "http://example.com"}
    raise ValueError(f"No built-in argument builder for tool {tool!r}. Use --params-json.")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an approved MCP tool invocation.")
    parser.add_argument(
        "--url", default=None, help="MCP server URL (default: env or 192.168.3.137:8000/mcp)"
    )
    parser.add_argument(
        "--tool", default="browser_navigate", help="State-changing MCP tool to invoke"
    )
    parser.add_argument(
        "--target-url",
        default="http://example.com",
        help="URL argument for navigation/download tools",
    )
    parser.add_argument("--params-json", default=None, help="Override tool arguments as raw JSON")
    parser.add_argument(
        "--policy-tools", default="policies/tools.yaml", help="Path to tools policy YAML"
    )
    parser.add_argument(
        "--policy-agents", default="policies/agents.yaml", help="Path to agents policy YAML"
    )
    parser.add_argument("--agent", default="researcher", help="Agent profile to evaluate against")
    parser.add_argument("--yes", action="store_true", help="Auto-grant approval (non-interactive)")
    parser.add_argument(
        "--json", default=None, dest="json_out", help="Write results to this JSON file"
    )
    args = parser.parse_args()

    if args.tool not in STATE_CHANGING_TOOLS:
        print(
            f"Refusing: {args.tool!r} is not in the approved state-changing tool set. "
            "Use scripts/verify_mcp.py for read-only tools.",
            file=sys.stderr,
        )
        return 2

    server_url = args.url or os.environ.get("ZUZU_MCP_SERVER_URL", "http://192.168.3.137:8000/mcp")
    client = McpClient(server_url=server_url, connect_timeout=10.0, request_timeout=30.0)
    results: dict = {"endpoint": client.server_url, "tool": args.tool}
    ok = False

    try:
        await client.start()
        results["handshake"] = "ok"
        results["server_info"] = client.server_info
        results["tools"] = sorted(client.tools.keys())

        spec = client.get_tool(args.tool)
        if spec is None:
            raise RuntimeError(f"Tool {args.tool!r} not discovered on the server.")
        results["input_schema"] = spec.input_schema

        if args.params_json:
            arguments = json.loads(args.params_json)
        else:
            arguments = build_arguments(args.tool, args.target_url)
        results["arguments"] = arguments

        client.validate_arguments(args.tool, arguments)
        results["schema_validation"] = "ok"

        # Evaluate the action against Zuzu's real default-deny policy.
        policy = load_policy_from_files(args.policy_tools, args.policy_agents)
        agent = policy.profiles.get(args.agent)
        action = Action(kind="mcp_tool", tool=args.tool, params=arguments)
        verdict = policy.evaluate(action, agent=agent)
        results["policy_decision"] = verdict.decision.value
        results["policy_reason"] = verdict.reason

        if verdict.decision == Decision.DENY:
            raise RuntimeError(f"Policy denied the action: {verdict.reason}")
        if verdict.decision != Decision.APPROVAL_REQUIRED:
            decision_value = verdict.decision.value
            raise RuntimeError(
                f"Expected approval_required for a state-changing tool, got {decision_value}"
            )

        # Approval gate.
        approved = args.yes
        if not approved:
            print(
                f"Approval requested for {args.tool}({arguments}).",
                file=sys.stderr,
            )
            if sys.stdin.isatty():
                response = input("Approve? [y/N]: ")
                approved = response.strip().lower() in ("y", "yes")
        if not approved:
            results["approval"] = "denied"
            raise RuntimeError("Approval denied by operator.")
        results["approval"] = "granted"

        result = await client.invoke(args.tool, arguments)
        results["call"] = {"tool": args.tool, "result": str(result)[:2000]}

        # Confirm the browser state changed for navigation tools.
        if args.tool == "browser_navigate":
            current = await client.invoke("browser_current", {})
            results["state_check"] = {"tool": "browser_current", "result": str(current)[:1000]}

        ok = True
    except Exception as exc:  # noqa: BLE001
        results["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await client.stop()

    print(json.dumps(results, indent=2, ensure_ascii=False))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
