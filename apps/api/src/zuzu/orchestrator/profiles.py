"""Agent profile loading.

Agent definitions live in `agents/*.md` (human documentation of purpose,
responsibilities, limits and output format) and `policies/agents.yaml`
(machine-enforceable allow/deny lists and limits). This module loads both and
keeps them in sync by name; the YAML profile is the authoritative, enforceable
set, while the markdown file is documentation and prompt material.
"""

from __future__ import annotations

import logging
import pathlib

from zuzu.policy.engine import AgentProfile, load_policy_from_files

logger = logging.getLogger("zuzu.orchestrator.profiles")

_REPO_ROOT = (
    pathlib.Path(__file__).resolve().parents[5]
)  # .../apps/api/src/zuzu/orchestrator -> repo
AGENTS_DIR = _REPO_ROOT / "agents"
POLICY_DIR = _REPO_ROOT / "policies"


def load_profiles() -> dict[str, AgentProfile]:
    """Load agent profiles from policies/agents.yaml."""
    engine = load_policy_from_files(str(POLICY_DIR / "tools.yaml"), str(POLICY_DIR / "agents.yaml"))
    return engine.profiles


def load_agent_markdown(name: str) -> str:
    """Load the agent's markdown definition (prompt material), if present."""
    path = AGENTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Agent markdown not found: %s", path)
    return ""


def get_profile(name: str) -> AgentProfile:
    profiles = load_profiles()
    if name not in profiles:
        raise KeyError(name)
    return profiles[name]
