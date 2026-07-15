"""delegate tool: hand a task to a specialized subagent.

The tool only knows a dispatch protocol; the concrete
``coding_agent.agent.subagent.SubAgentRunner`` is injected by the composition
root, keeping ``tools/`` independent from ``agent/``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from coding_agent.llm.base import LLMError
from coding_agent.tools.base import Tool, ToolError, require_string


class SubAgentDispatch(Protocol):
    """What the delegate tool needs from the subagent runner."""

    def run(self, agent: str, task: str) -> str: ...


class DelegateTool(Tool):
    """Delegation is read-only from the harness's point of view: every tool
    call made *inside* the subagent goes through guardrails, policies and
    supervision individually."""

    name = "delegate"
    read_only = True

    def __init__(self, dispatch: SubAgentDispatch, agents: Mapping[str, str]) -> None:
        self._dispatch = dispatch
        self._agents = dict(agents)
        roster = " ".join(f"'{name}': {role}" for name, role in self._agents.items())
        self.description = (
            "Delegate a task to a specialized subagent and get its report back. "
            f"Available subagents: {roster}"
        )
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": sorted(self._agents),
                    "description": "Which subagent to delegate to.",
                },
                "task": {
                    "type": "string",
                    "description": "A clear, self-contained description of the task to perform.",
                },
            },
            "required": ["agent", "task"],
        }

    def execute(self, arguments: dict[str, Any]) -> str:
        agent = require_string(arguments, "agent")
        task = require_string(arguments, "task")
        if agent not in self._agents:
            known = ", ".join(sorted(self._agents))
            raise ToolError(f"Unknown subagent '{agent}'. Available subagents: {known}")
        try:
            report = self._dispatch.run(agent, task)
        except LLMError as exc:
            raise ToolError(f"Subagent '{agent}' failed: {exc}") from exc
        return f"[{agent} report]\n{report}"
