"""Memory endpoint + service tests."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_memory_create_list_delete(client: httpx.AsyncClient, auth_headers) -> None:
    created = await client.post(
        "/api/v1/memories",
        headers=auth_headers,
        json={"content": "The user's favourite color is teal."},
    )
    assert created.status_code == 201
    mem_id = created.json()["id"]

    listed = await client.get("/api/v1/memories", headers=auth_headers)
    assert listed.status_code == 200
    assert any(m["id"] == mem_id for m in listed.json()["memories"])

    deleted = await client.delete(f"/api/v1/memories/{mem_id}", headers=auth_headers)
    assert deleted.status_code == 200

    listed2 = await client.get("/api/v1/memories", headers=auth_headers)
    assert not any(m["id"] == mem_id for m in listed2.json()["memories"])


@pytest.mark.asyncio
async def test_memory_delete_unknown_404(client: httpx.AsyncClient, auth_headers) -> None:
    import uuid as uuidlib

    resp = await client.delete(f"/api/v1/memories/{uuidlib.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_memory_keyword_search(client: httpx.AsyncClient, auth_headers) -> None:
    await client.post(
        "/api/v1/memories", headers=auth_headers, json={"content": "Homelab runs Proxmox."}
    )
    await client.post(
        "/api/v1/memories", headers=auth_headers, json={"content": "Favourite tea is oolong."}
    )
    resp = await client.get("/api/v1/memories", headers=auth_headers, params={"query": "proxmox"})
    contents = [m["content"] for m in resp.json()["memories"]]
    assert any("Proxmox" in c for c in contents)
    assert not any("oolong" in c for c in contents)


@pytest.mark.asyncio
async def test_memory_relevance_scores() -> None:
    from zuzu.memory.service import relevance_score

    q = {"homelab", "proxmox"}
    assert relevance_score(q, "The homelab runs Proxmox and Docker.") == 1.0
    assert relevance_score(q, "Something entirely different.") == 0.0
    assert relevance_score(set(), "anything") == 0.0
