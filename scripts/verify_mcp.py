"""Live MCP verification script.

Performs a full MCP handshake against the configured server, discovers tools,
(optionally) calls a read-only tool, and prints evidence. Read-only by default.

Usage:
  python scripts/verify_mcp.py [--call READONLY_TOOL] [--json OUTFILE]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=None)
    parser.add_argument(
        "--call", default=None, help="Read-only tool to call (e.g. browser_current)"
    )
    parser.add_argument("--json", default=None, help="Write results to this file")
    args = parser.parse_args()

    url = args.url or os.environ.get("ZUZU_MCP_SERVER_URL", "http://192.168.3.137:8000/mcp")

    from zuzu.integrations.mcp.client import McpClient

    client = McpClient(server_url=url, connect_timeout=10.0, request_timeout=30.0)
    results: dict = {"endpoint": client.server_url}

    try:
        await client.start()
        results["handshake"] = "ok"
        results["server_info"] = client.server_info
        results["tools"] = sorted(client.tools.keys())
        if args.call:
            readonly_tools = {"browser_current", "browser_read", "browser_tabs", "browser_find"}
            if args.call not in readonly_tools:
                print(f"Refusing to call non-read-only tool {args.call!r} in verify script.")
                return 2
            result = await client.invoke(args.call, {})
            results["call"] = {"tool": args.call, "result": str(result)[:1000]}
        ok = True
    except Exception as exc:  # noqa: BLE001
        results["error"] = f"{type(exc).__name__}: {exc}"
        ok = False
    finally:
        await client.stop()

    print(json.dumps(results, indent=2, ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
