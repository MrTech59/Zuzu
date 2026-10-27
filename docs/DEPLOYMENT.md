# Zuzu Deployment

## Principles

- Dedicated Zuzu environment in the Proxmox homelab (its own VM/LXC).
- **Tailscale-only** access: no public port forwarding, no Tailscale Funnel.
- Own database, own credentials, own volumes.
- Existing OpenClaw / MCP containers are not modified.
- Deployment is manual after explicit approval (not automated).

## Local development (Windows)

```powershell
python -m pip install -e ".[dev]"
scripts\dev.ps1            # migrations + API on 127.0.0.1:8000 (mock provider + SQLite by default)
```

Set real credentials in `.env` (copy `.env.example`) to use the live NVIDIA
provider. With Docker Desktop running: `docker compose up -d --build` for the
full stack (db + api + web).

## Production layout (Proxmox VM/LXC)

```text
zuzu-vm (dedicated)
├── db         postgres:16 (volume: db-data, no host port published)
├── api        zuzu API container (non-root; port bound to Tailscale interface only)
└── web        zuzu web container (same)
```

Required resources (suggested): 2 vCPU, 4 GB RAM, 20 GB disk.

## Access control

1. Bind the API/web ports to the Tailscale interface only, e.g. compose
   `ports: ["100.x.y.z:8000:8000"]` or firewall all non-Tailscale ingress.
2. Set `APP_ENV=production` and a strong `ZUZU_API_KEY`
   (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
3. Generate a unique `POSTGRES_PASSWORD`; never use the example value.
4. The DB publishes no ports on the compose network's host; DB is reachable
   only inside the compose network.

## Pre-deploy checklist (requires owner approval)

- [ ] Dedicated VM/LXC created for Zuzu
- [ ] `.env` with generated secrets (not committed)
- [ ] `docker compose up -d --build`
- [ ] `GET /api/v1/health` returns 200 via Tailscale
- [ ] `GET /api/v1/ready` reports database ok (auth required)
- [ ] Unauthenticated request to `/api/v1/chat` returns 401
- [ ] No ports exposed publicly (verify from outside the tailnet)

## Backups

`scripts/backup.sh` on the VM (cron/systemd timer recommended):
`pg_dump -Fc` of the zuzu DB, 14-day retention. Restore:
`pg_restore -U zuzu -d zuzu --clean <file>`.

## Health & rollback

- Healthcheck: `/api/v1/health` (liveness), `/api/v1/ready` (DB + MCP).
- Rollback: `git checkout <previous-tag> && docker compose up -d --build`;
  migrations are currently forward-only in practice — verify a downgrade on a
  copy before relying on it in production.
