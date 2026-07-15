"""ask_user tool: let the agent ask the user a clarifying question mid-turn.

Used when the agent lacks evidence to continue (ambiguous request, missing
information, risky change). Duck-typed on the ``ask`` method so any
``AgentIO`` implementation satisfies it.
"""

from __future__ import annotations

from typing import Any, Protocol

from coding_agent.tools.base import Tool, require_string


class Questioner(Protocol):
    def ask(self, prompt: str) -> str: ...


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Ask the user one clarifying question and return their answer. Use it when the "
        "request is ambiguous or you are missing information you cannot obtain with "
        "your other tools. Ask sparingly and be specific."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question for the user."},
        },
        "required": ["question"],
    }
    read_only = True

    def __init__(self, io: Questioner) -> None:
        self._io = io

    def execute(self, arguments: dict[str, Any]) -> str:
        question = require_string(arguments, "question")
        answer = self._io.ask(f"\n[agent question] {question}\n> ").strip()
        if not answer:
            return "The user did not answer. Proceed with your best judgment or stop and explain."
        return f"User answered: {answer}"
