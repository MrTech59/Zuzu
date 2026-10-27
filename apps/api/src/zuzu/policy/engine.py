"""Zuzu policy engine — default deny.

Policy sources:
- policies/tools.yaml : per-tool allow/deny, workspace scoping, approval needs
- policies/agents.yaml: per-agent tool allowlists/denylists and limits

Rules:
1. Every action is denied unless some rule explicitly allows it.
2. Agent profiles constrain which tools an agent may even *ask* for; the
   backend policy engine is the actual security boundary (profiles are not).
3. Approval requirements are attached to actions, evaluated at execution time.
4. Agent prompts can never grant permissions this engine denies.

The engine is pure (no I/O) so it is unit-testable.
"""

from __future__ import annotations

import enum
import fnmatch
from dataclasses import dataclass, field
from typing import Any

import yaml


class Decision(enum.StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True, slots=True)
class Action:
    """An action the system wants to perform."""

    kind: str  # e.g. "mcp_tool", "file_write", "service_restart"
    tool: str | None = None  # e.g. "browser_navigate"
    resource: str | None = None  # e.g. target path or URL
    params: dict[str, Any] = field(default_factory=dict)

    def resource_str(self) -> str:
        return self.resource or ""


@dataclass(frozen=True, slots=True)
class PolicyRule:
    when_kind: str
    tool_pattern: str | None = None
    resource_pattern: str | None = None
    decision: Decision = Decision.DENY
    reason: str | None = None

    def matches(self, action: Action) -> bool:
        if action.kind != self.when_kind:
            return False
        if self.tool_pattern is not None:
            if action.tool is None or not fnmatch.fnmatch(action.tool, self.tool_pattern):
                return False
        if self.resource_pattern is not None:
            if not fnmatch.fnmatch(action.resource_str().lower(), self.resource_pattern.lower()):
                return False
        return True


@dataclass(slots=True)
class AgentProfile:
    """Agent definition loaded from policies/agents.yaml + agents/*.md."""

    name: str
    description: str = ""
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()
    allowed_action_kinds: frozenset[str] = frozenset()
    workspace_paths: tuple[str, ...] = ()
    max_steps: int = 12
    timeout_seconds: int = 600
    requires_approval_for: frozenset[str] = frozenset()
    output_format: str = "markdown"


@dataclass(slots=True)
class PolicyVerdict:
    decision: Decision
    reason: str
    rule: str | None = None


class PolicyEngine:
    """Pure, default-deny evaluation of actions against rules and agent profiles."""

    def __init__(
        self,
        rules: list[PolicyRule],
        profiles: dict[str, AgentProfile],
        default_decision: Decision = Decision.DENY,
    ) -> None:
        self.rules = rules
        self.profiles = profiles
        self.default_decision = default_decision

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_yaml(cls, tools_yaml: str, agents_yaml: str) -> PolicyEngine:
        tools_doc = yaml.safe_load(tools_yaml) or {}
        agents_doc = yaml.safe_load(agents_yaml) or {}

        rules: list[PolicyRule] = []
        for raw in tools_doc.get("rules", []):
            decision = Decision(str(raw.get("decision", "deny")))
            rules.append(
                PolicyRule(
                    when_kind=str(raw.get("when", {}).get("kind", "*")),
                    tool_pattern=raw.get("when", {}).get("tool"),
                    resource_pattern=raw.get("when", {}).get("resource"),
                    decision=decision,
                    reason=raw.get("reason"),
                )
            )

        profiles: dict[str, AgentProfile] = {}
        for name, raw in (agents_doc.get("agents") or {}).items():
            raw = raw or {}
            profiles[str(name)] = AgentProfile(
                name=str(name),
                description=str(raw.get("description", "")),
                allowed_tools=frozenset(raw.get("allowed_tools", [])),
                denied_tools=frozenset(raw.get("denied_tools", [])),
                allowed_action_kinds=frozenset(raw.get("allowed_action_kinds", [])),
                workspace_paths=tuple(raw.get("workspace_paths", [])),
                max_steps=int(raw.get("max_steps", 12)),
                timeout_seconds=int(raw.get("timeout_seconds", 600)),
                requires_approval_for=frozenset(raw.get("requires_approval_for", [])),
                output_format=str(raw.get("output_format", "markdown")),
            )
        return cls(rules=rules, profiles=profiles)

    # ------------------------------------------------------------ evaluation
    def evaluate(self, action: Action, agent: AgentProfile | None = None) -> PolicyVerdict:
        """Evaluate an action. Default deny; first matching rule wins."""
        if agent is not None:
            # Agent profile constraints (coarse filters, not the boundary).
            if action.kind not in agent.allowed_action_kinds and agent.allowed_action_kinds:
                return PolicyVerdict(
                    Decision.DENY,
                    f"Agent '{agent.name}' is not permitted to perform '{action.kind}' actions.",
                )
            if action.tool and action.tool in agent.denied_tools:
                return PolicyVerdict(
                    Decision.DENY,
                    f"Tool '{action.tool}' is denied for agent '{agent.name}'.",
                )
            if action.tool and agent.allowed_tools and action.tool not in agent.allowed_tools:
                return PolicyVerdict(
                    Decision.DENY,
                    f"Tool '{action.tool}' is not in the allowlist of agent '{agent.name}'.",
                )

        for rule in self.rules:
            if rule.matches(action):
                # Even an ALLOW rule cannot override an explicit agent denial
                # for approval-required kinds when profile demands approval.
                if agent is not None and action.kind in agent.requires_approval_for:
                    return PolicyVerdict(
                        Decision.APPROVAL_REQUIRED,
                        f"Action '{action.kind}' requires explicit approval for "
                        f"agent '{agent.name}'.",
                        rule="agent-profile-approval",
                    )
                return PolicyVerdict(rule.decision, rule.reason or "policy rule", rule.when_kind)

        return PolicyVerdict(
            self.default_decision,
            "No policy rule allows this action (default deny).",
        )


def load_policy_from_files(tools_path: str, agents_path: str) -> PolicyEngine:
    with open(tools_path, encoding="utf-8") as f:
        tools_yaml = f.read()
    with open(agents_path, encoding="utf-8") as f:
        agents_yaml = f.read()
    return PolicyEngine.from_yaml(tools_yaml, agents_yaml)
