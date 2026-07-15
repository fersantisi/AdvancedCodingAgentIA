"""Supervision mode (human in the loop).

When enabled, mutating tools (``read_only == False``) require explicit user
approval before running. Read-only tools never prompt.
"""

from __future__ import annotations

import logging

from coding_agent.agent.io import AgentIO
from coding_agent.models import ToolCall
from coding_agent.tools import Tool
from coding_agent.utils import truncate

logger = logging.getLogger(__name__)

_SUMMARY_LIMIT = 300


class Supervisor:
    def __init__(self, io: AgentIO, enabled: bool = True) -> None:
        self._io = io
        self.enabled = enabled

    def approve(self, tool: Tool, call: ToolCall) -> bool:
        """Return True if the tool call may run."""
        if not self.enabled or tool.read_only:
            return True
        approved = self._io.confirm(f"Approve {_describe(call)}? [Y/n] ")
        logger.info("Supervision: %s -> %s", call.name, "approved" if approved else "denied")
        return approved

    def toggle(self, enabled: bool) -> None:
        self.enabled = enabled


def _describe(call: ToolCall) -> str:
    if call.name == "run_command":
        return f"run_command: {truncate(str(call.arguments.get('command', '?')), _SUMMARY_LIMIT)}"
    if call.name == "write_file":
        content = call.arguments.get("content", "")
        size = len(content) if isinstance(content, str) else "?"
        return f"write_file: {call.arguments.get('path', '?')} ({size} chars)"
    return f"{call.name}: {truncate(str(call.arguments), _SUMMARY_LIMIT)}"
