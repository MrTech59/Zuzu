"""Stage 1 tests: app startup, health, auth, and independence."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_is_public_and_safe(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    # Health must not leak credentials or private infrastructure details.
    text = resp.text.lower()
    for forbidden in ("api_key", "bearer", "password", "nvidia", "tailscale", "192.168"):
        assert forbidden not in text, f"health leaked '{forbidden}'"


@pytest.mark.asyncio
async def test_ready_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/ready")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"

    from zuzu.config import get_settings

    headers = {"Authorization": f"Bearer {get_settings().zuzu_api_key}"}
    resp = await client.get("/api/v1/ready", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["mcp"] == "disabled"


@pytest.mark.asyncio
async def test_wrong_token_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/ready", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_rejects_when_no_key_configured_outside_dev(
    monkeypatch: pytest.MonkeyPatch, sqlite_db
) -> None:
    """In production mode without an API key the app must refuse to start."""
    from zuzu.config import Settings, reset_settings_cache

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ZUZU_API_KEY", raising=False)
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="ZUZU_API_KEY"):
        Settings().assert_runnable()
    reset_settings_cache()


@pytest.mark.asyncio
async def test_independence_core_works_without_external_agents(
    client: httpx.AsyncClient, auth_headers
) -> None:
    """Core functionality works with OpenClaw, AstraAI and MCP all unavailable.

    Zuzu must not depend on any other assistant. This test exercises chat,
    tasks, memories with the mock provider and MCP disabled.
    """
    # Health + chat + tasks + memories all respond.
    health = await client.get("/api/v1/health")
    assert health.status_code == 200

    chat = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "echo:hello from an independent Zuzu"},
    )
    assert chat.status_code == 200
    assert chat.json()["assistant_message"]["content"].endswith("hello from an independent Zuzu")

    tasks = await client.get("/api/v1/tasks", headers=auth_headers)
    assert tasks.status_code == 200

    mem = await client.post(
        "/api/v1/memories",
        headers=auth_headers,
        json={"content": "Zuzu runs independently."},
    )
    assert mem.status_code == 201

    listing = await client.get("/api/v1/memories", headers=auth_headers)
    assert listing.status_code == 200
    assert any("independently" in m["content"] for m in listing.json()["memories"])


def test_no_external_agent_references_in_source() -> None:
    """Source must not reference OpenClaw, AstraAI or other assistant projects."""
    import pathlib
    import re

    src_root = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "src"
    pattern = re.compile(r"(?i)openclaw|astraai|astra_ai|astrai")
    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            offenders.append(str(path))
    assert not offenders, f"Forbidden references found in: {offenders}"
