"""Deterministic mock AI provider.

Used for offline development, CI and tests. Never contacts the network and
never requires credentials. Behaviour is fully deterministic and reflects the
request content, which makes assertions about prompt construction possible.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

from zuzu.ai.base import ChatMessage, ChatProvider, ChatRequest, ChatResponse, StreamDelta

MOCK_MODEL = "zuzu-mock-1"


class MockProvider(ChatProvider):
    """Deterministic offline provider.

    Response conventions:
    - If the last user message starts with "FAKE_ERROR:", raises ProviderError
      with the remainder as the message (for testing error paths).
    - If the last user message contains "echo:", replies with the text after it.
    - Otherwise replies with a deterministic acknowledgement including the
      number of prompt messages.
    """

    name = "mock"

    async def complete(self, request: ChatRequest) -> ChatResponse:
        last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
        text = last_user.content if last_user else ""

        # Planning requests get a deterministic JSON plan.
        if text.startswith("Create an execution plan"):
            if "navigate" in text:
                plan = {
                    "steps": [
                        {
                            "name": "open-page",
                            "tool": "browser_navigate",
                            "kind": "mcp_tool",
                            "params": {"url": "https://example.com"},
                        },
                        {
                            "name": "check-page",
                            "tool": "browser_current",
                            "kind": "mcp_tool",
                            "params": {},
                        },
                        {"name": "respond", "tool": None, "kind": "respond", "params": {}},
                    ]
                }
            elif "use browser tools" in text:
                plan = {
                    "steps": [
                        {
                            "name": "check-page",
                            "tool": "browser_current",
                            "kind": "mcp_tool",
                            "params": {},
                        },
                        {"name": "respond", "tool": None, "kind": "respond", "params": {}},
                    ]
                }
            else:
                plan = {
                    "steps": [{"name": "respond", "tool": None, "kind": "respond", "params": {}}]
                }
            return ChatResponse(
                content=json.dumps(plan),
                model=MOCK_MODEL,
                provider="mock",
                finish_reason="stop",
            )

        if text.startswith("FAKE_ERROR:"):
            from zuzu.errors import ProviderError

            raise ProviderError(text[len("FAKE_ERROR:") :].strip() or "Mock provider error.")

        if "echo:" in text:
            reply = text.split("echo:", 1)[1].strip()
        else:
            reply = f"Mock reply to {len(request.messages)} prompt message(s)."
            if request.messages and request.messages[0].role == "system":
                sys_text = request.messages[0].content
                agent_name = re.search(r"agent name:\s*(\w[\w-]*)", sys_text, re.IGNORECASE)
                if agent_name:
                    reply += f" [agent={agent_name.group(1)}]"

        return ChatResponse(
            content=reply,
            model=MOCK_MODEL,
            provider="mock",
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    async def _stream(self, request: ChatRequest) -> AsyncIterator[StreamDelta]:
        response = await self.complete(request)
        # Deterministic chunking: split into 12-char chunks to exercise SSE paths.
        for i in range(0, len(response.content), 12):
            yield StreamDelta(content=response.content[i : i + 12])
        yield StreamDelta(content="", finish_reason="stop")

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamDelta]:
        return self._stream(request)

    async def healthcheck(self) -> bool:
        return True


def messages_to_provider(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Plain-dict view for tests and API serialization."""
    return [{"role": m.role, "content": m.content} for m in messages]
