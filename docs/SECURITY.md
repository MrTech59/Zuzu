# Zuzu Security

## Threat model (v0.1.0)

Assets: user data (conversations, memories), API availability, the host, the
homelab, and the NVIDIA/MCP credentials. Adversaries: prompt-injection content
fetched from the web, a compromised model output, or a malicious client on the
network.

## Controls

### Authentication
- All `/api/v1` routes except `/api/v1/health` require `Authorization: Bearer
  <ZUZU_API_KEY>` (constant-time comparison).
- Auth is enforced whenever `ZUZU_API_KEY` is set **or** `APP_ENV` is not a
  development environment. An internal/LAN IP is never treated as
  authentication.
- In production, startup refuses to run without a configured key.
- Remote access design: Tailscale-only. No public port forwarding, no Funnel.

### Authorization (policy engine)
- **Default deny.** Everything not explicitly allowed in `policies/tools.yaml`
  is rejected in backend code — agent profiles and prompts are *not* a
  boundary.
- Auto-allow: read-only browser tools, and internal `respond` composition.
- Approval required: navigation, clicks, typing, downloads, screenshots, file
  writes, shell execution, service restarts.
- Denied outright: network changes, public exposure, Docker-socket access,
  destructive storage ops, unrestricted host/admin access.
- Workspace scoping: developer/tester file access is restricted to configured
  workspace roots (`policies/agents.yaml`).

### Approvals
- Bound to the exact action: kind + tool + resource + params fingerprint
  (SHA-256). Stored `params_hash` is re-checked at consumption.
- **Single-use** (status `used` after consumption), **expiring**
  (`APPROVAL_TTL_SECONDS`, default 900s), stale decisions rejected.
- The model cannot approve its own actions: decisions only enter through the
  authenticated decision endpoint.

### Untrusted content
- Web/tool output is data, never instructions: it is not injected into the
  system prompt; it cannot grant permissions or override policy.
- Model outputs cannot execute actions directly; every side effect goes
  through policy + (when required) human approval.

### Secrets
- `NVIDIA_API_KEY`, `ZUZU_API_KEY` etc. are read only from the environment.
- Never exposed to the frontend: the web app stores its API token client-side
  and never receives provider keys.
- Redacted from logs (`zuzu.logging` filter) and audit payloads
  (`zuzu.audit.service.redact_value`) — tested.
- Never written to messages/memories/audit rows.

### Isolation
- Zuzu runs with its own database and identity. Container images run as
  non-root (`zuzu` user).
- The Docker socket is never mounted into the API/agent runtime, and Proxmox
  credentials are never held by Zuzu.
- The MCP server is treated as an untrusted tool service; it is never
  modified and receives only approved, schema-validated tool calls.

## Known limitations (v0.1.0)
- Single static bearer token (per-user accounts/JWT deferred).
- Tasks execute in-process (not in an isolated worker container) — acceptable
  for the current read-only-with-approval scope; isolate before enabling
  write-heavy agents.
- Rate limiting on the API is not implemented; rely on network access
  control (Tailscale) until then.
- Audit log is append-only by convention, not enforced by DB privileges.
