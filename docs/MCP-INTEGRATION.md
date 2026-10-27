# Zuzu MCP Integration

Status: **verified against the live server** (2026-10-27), including
read-only discovery and an approved state-changing tool invocation
(`browser_navigate`).

## Verified findings

| Item | Value |
| --- | --- |
| Configured host | `192.168.3.137:8000` (TCP reachable) |
| Actual endpoint | `http://192.168.3.137:8000/mcp` |
| Transport | **Streamable HTTP** (MCP spec), NOT legacy HTTP+SSE |
| Protocol versions | Client offered `2025-03-26`; server negotiated `2025-11-25` |
| Server | `picoclaw-browser` v1.30.0 (uvicorn) |
| Sessions | Required; `mcp-session-id` response header, echoed on every request |
| Handshake | `initialize` → 200 + session id; `notifications/initialized` → 202 |
| Tool discovery | `tools/list` → 22 tools with JSON input schemas |
| Live tool call | `browser_current` → 200 with real browser state |

Evidence captured in `docs/mcp-live-evidence.json` (handshake + tool list + a
read-only `browser_current` result). Reproduce with `python scripts/verify_mcp.py`.

Historical notes that turned out to be wrong: "session-based SSE transport"
and "endpoint at the root URL". All non-`/mcp` paths return 404
(`/`, `/sse`, `/docs`, `/openapi.json`, `/health`).

## Discovered tools (22)

`browser_navigate`, `browser_read`, `browser_read_chunk`, `browser_click`,
`browser_type`, `browser_press`, `browser_select`, `browser_scroll`,
`browser_back`, `browser_current`, `browser_find`, `browser_links`,
`browser_links_all`, `browser_extract_links`, `browser_get_attribute`,
`browser_screenshot`, `browser_download`, `browser_tabs`, `browser_new_tab`,
`browser_switch_tab`, `browser_wait`, `browser_wait_for`.

Full schemas are snapshotted in `docs/mcp-tools-snapshot.json`.

`browser_navigate` schema (verified):

```json
{
  "type": "object",
  "properties": {"url": {"type": "string"}},
  "required": ["url"]
}
```

## Zuzu's MCP implementation

- `apps/api/src/zuzu/integrations/mcp/client.py` — Zuzu's own MCP client on top
  of the official `mcp` SDK (Streamable HTTP), implementing initialize
  handshake, tool discovery, schema validation, bounded timeouts/retries and
  session lifecycle.
- `apps/api/src/zuzu/integrations/mcp/registry.py` — application-level
  registry: health tracking, tool listing, invocation facade; returns `None`
  when disabled so the app degrades gracefully.
- `apps/api/src/zuzu/integrations/mcp/mock.py` — deterministic mock registry
  used by the test suite and offline development.

## Security model for MCP tools

- Every invocation passes the policy engine (`zuzu.policy.engine`) first;
  MCP tools are capabilities, not permission grants.
- Read-only tools (`browser_current`, `browser_read`, `browser_tabs`,
  `browser_find`, `browser_links*`, `browser_extract_links`,
  `browser_get_attribute`, `browser_read_chunk`, `browser_wait*`) may run
  automatically.
- State-changing tools (`browser_navigate`, `browser_click`, `browser_type`,
  `browser_press`, `browser_select`, `browser_scroll`, `browser_screenshot`,
  `browser_download`, tab management) require explicit user approval in
  v0.1.0 — deliberately conservative.
- Tool arguments are validated against the discovered JSON schema before any
  call; schema-invalid arguments are rejected with a 422-class error.
- Tool output is treated as untrusted data: it is never injected into the
  system prompt and can never grant permissions.
- Invocations and outcomes are recorded in the audit log (redacted).
- The MCP server was NOT modified: read-only client-side integration only.

## Running / verifying

```powershell
# Live verification (read-only):
python scripts/verify_mcp.py --call browser_current --json docs/mcp-live-evidence.json
```

If the MCP server is unreachable, Zuzu starts and operates normally; MCP tool
steps inside tasks fail with a clear, honest reason ("MCP tool server is
unavailable").

## Approved tool verification

State-changing tools require explicit approval under Zuzu's default-deny
policy. The approved-tool script exercises the full gate:

```powershell
python scripts/verify_mcp_approved.py --tool browser_navigate --target-url http://example.com --yes --json docs/mcp-approved-evidence.json
```

The script:

1. Connects via Zuzu's own `McpClient` (Streamable HTTP).
2. Discovers the real tool schemas and validates arguments against the
discovered JSON schema.
3. Evaluates the action with Zuzu's `PolicyEngine` (`policies/tools.yaml`).
4. Records an explicit approval (`--yes` for non-interactive use; interactive
prompt when run from a terminal).
5. Invokes the approved tool directly through the MCP client.
6. Confirms the browser state changed (e.g. `browser_current` after
`browser_navigate`).

Evidence from the latest approved run is captured in
`docs/mcp-approved-evidence.json`. The MCP server itself is never modified.

