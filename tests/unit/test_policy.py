"""Policy engine tests: default deny, allowlists, approval requirements."""

from __future__ import annotations

import pytest

from zuzu.policy.engine import Action, Decision, PolicyEngine


@pytest.fixture()
def engine() -> PolicyEngine:
    from zuzu.orchestrator.profiles import POLICY_DIR, load_policy_from_files

    return load_policy_from_files(str(POLICY_DIR / "tools.yaml"), str(POLICY_DIR / "agents.yaml"))


def test_default_deny_unknown_kind(engine: PolicyEngine) -> None:
    verdict = engine.evaluate(Action(kind="totally_unknown"))
    assert verdict.decision is Decision.DENY


def test_readonly_browser_tools_allowed(engine: PolicyEngine) -> None:
    for tool in ("browser_read", "browser_current", "browser_tabs", "browser_find"):
        verdict = engine.evaluate(Action(kind="mcp_tool", tool=tool))
        assert verdict.decision is Decision.ALLOW, tool


def test_navigate_requires_approval(engine: PolicyEngine) -> None:
    verdict = engine.evaluate(Action(kind="mcp_tool", tool="browser_navigate"))
    assert verdict.decision is Decision.APPROVAL_REQUIRED


def test_write_actions_require_approval(engine: PolicyEngine) -> None:
    for kind in ("file_write", "service_restart", "shell_exec"):
        verdict = engine.evaluate(Action(kind=kind))
        assert verdict.decision is Decision.APPROVAL_REQUIRED, kind


def test_dangerous_kinds_denied(engine: PolicyEngine) -> None:
    for kind in (
        "network_change",
        "public_exposure",
        "docker_socket_access",
        "destructive_storage",
        "host_admin",
    ):
        verdict = engine.evaluate(Action(kind=kind))
        assert verdict.decision is Decision.DENY, kind


def test_agent_allowlist_enforced(engine: PolicyEngine) -> None:
    profiles = engine.profiles
    researcher = profiles["researcher"]
    # Researcher may ask for read tools.
    assert (
        engine.evaluate(Action(kind="mcp_tool", tool="browser_read"), researcher).decision
        is Decision.ALLOW
    )
    # But clicking is outside its allowlist AND denied in tools.yaml → deny.
    assert (
        engine.evaluate(Action(kind="mcp_tool", tool="browser_click"), researcher).decision
        is Decision.DENY
    )
    # Homelab observer may not open new tabs.
    observer = profiles["homelab-observer"]
    assert (
        engine.evaluate(Action(kind="mcp_tool", tool="browser_new_tab"), observer).decision
        is Decision.DENY
    )


def test_profile_approval_requirements(engine: PolicyEngine) -> None:
    dev = engine.profiles["developer"]
    verdict = engine.evaluate(Action(kind="file_write"), dev)
    assert verdict.decision is Decision.APPROVAL_REQUIRED


def test_unknown_tool_denied_for_agents_with_empty_allowlist(engine: PolicyEngine) -> None:
    # A tool not in any allowlist is denied when the agent defines an allowlist.
    dev = engine.profiles["developer"]
    verdict = engine.evaluate(Action(kind="mcp_tool", tool="browser_navigate"), dev)
    assert verdict.decision is Decision.DENY


def test_all_four_profiles_exist(engine: PolicyEngine) -> None:
    assert set(engine.profiles) == {
        "researcher",
        "developer",
        "tester",
        "homelab-observer",
    }
