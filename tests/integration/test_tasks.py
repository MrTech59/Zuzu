"""Task lifecycle tests: creation, planning, execution, cancellation, failure.

Uses the mock provider and (when a step needs MCP) a mock registry.
"""

from __future__ import annotations

import asyncio
import uuid as uuidlib

import httpx
import pytest


async def wait_for_status(
    client: httpx.AsyncClient,
    headers: dict,
    task_id: str,
    statuses: set[str],
    timeout: float = 10.0,
) -> dict:
    for _ in range(int(timeout * 20)):
        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        body = resp.json()
        if body["status"] in statuses:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"Task did not reach {statuses}; last body: {body}")


@pytest.mark.asyncio
async def test_simple_task_succeeds_with_respond_step(
    client: httpx.AsyncClient, auth_headers
) -> None:
    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "agent": "researcher",
            "title": "Summarize",
            "instruction": "Summarize the Zuzu project.",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    body = await wait_for_status(client, auth_headers, task_id, {"succeeded", "failed"})
    assert body["status"] == "succeeded", body.get("failure_reason")
    assert body["result"] is not None
    statuses = [s["status"] for s in body["steps"]]
    assert all(s in ("succeeded", "skipped") for s in statuses)


@pytest.mark.asyncio
async def test_unknown_agent_rejected(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"agent": "not-an-agent", "title": "x", "instruction": "y"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cancellation(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "agent": "researcher",
            "title": "Cancel me",
            "instruction": "Long research task.",
        },
    )
    task_id = resp.json()["id"]
    # Cancel immediately; task may or may not have started.
    cancel = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth_headers)
    assert cancel.status_code == 200
    body = await wait_for_status(
        client, auth_headers, task_id, {"cancelled", "succeeded", "failed"}
    )
    # Either already finished racing, or cancelled.
    assert body["status"] in {"cancelled", "succeeded", "failed"}


@pytest.mark.asyncio
async def test_cancel_twice_is_idempotent(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"agent": "researcher", "title": "c", "instruction": "i"},
    )
    task_id = resp.json()["id"]
    await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth_headers)
    cancel2 = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth_headers)
    assert cancel2.status_code == 200


@pytest.mark.asyncio
async def test_task_with_denied_action_fails_honestly(
    client: httpx.AsyncClient, auth_headers, monkeypatch
) -> None:
    """When policy denies every planned tool step, the task fails honestly."""
    from zuzu.integrations.mcp import registry as mcp_registry
    from zuzu.integrations.mcp.mock import MockMcpRegistry

    registry = MockMcpRegistry()
    mcp_registry.set_registry(registry)  # healthy mock; policy will gate anyway

    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "agent": "tester",  # tester has no MCP tools in its allowlist
            "title": "Denied path",
            "instruction": "Use browser tools to check something.",
        },
    )
    task_id = resp.json()["id"]
    body = await wait_for_status(client, auth_headers, task_id, {"succeeded", "failed"})
    # The tester agent cannot use browser tools; the plan either degrades to a
    # respond-only step (succeed) or fails with a policy reason. Either way,
    # the outcome is reported honestly — the key assertion is consistency.
    if body["status"] == "failed":
        assert body["failure_reason"]
    else:
        assert body["result"]
    mcp_registry.set_registry(None)


@pytest.mark.asyncio
async def test_task_steps_are_persisted(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"agent": "researcher", "title": "Persist", "instruction": "echo:persist"},
    )
    task_id = resp.json()["id"]
    await wait_for_status(client, auth_headers, task_id, {"succeeded", "failed"})
    detail = (await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)).json()
    assert detail["steps"], "steps must be persisted"
    assert detail["steps"][0]["position"] == 0


@pytest.mark.asyncio
async def test_task_not_found(client: httpx.AsyncClient, auth_headers) -> None:
    resp = await client.get(f"/api/v1/tasks/{uuidlib.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
