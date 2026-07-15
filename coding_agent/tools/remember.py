"""remember tool: save durable project knowledge to the persistent memory.

The tool receives the memory store and the valid categories by injection, so
``tools/`` stays independent from ``agent/``. It only writes the agent's own
memory file (never project files), which is why it is exempt from supervision.
"""

from __future__ import annotations

from typing import Any, Protocol

from coding_agent.tools.base import Tool, ToolError, require_string


class MemoryStore(Protocol):
    def remember(self, category: str, note: str) -> None: ...


class RememberTool(Tool):
    name = "remember"
    read_only = True  # mutates only the agent's own memory file, not the project

    def __init__(self, memory: MemoryStore, categories: tuple[str, ...]) -> None:
        self._memory = memory
        self.description = (
            "Save one durable fact about the project to persistent memory so future "
            "sessions can reuse it (detected architecture, key files, dependencies, "
            "useful commands, conventions, decisions taken, investigated bugs)."
        )
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": list(categories),
                    "description": "Kind of fact being saved.",
                },
                "note": {
                    "type": "string",
                    "description": "The fact to remember, one concise self-contained sentence.",
                },
            },
            "required": ["category", "note"],
        }

    def execute(self, arguments: dict[str, Any]) -> str:
        category = require_string(arguments, "category")
        note = require_string(arguments, "note")
        try:
            self._memory.remember(category, note)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return f"Remembered under '{category}': {note}"
