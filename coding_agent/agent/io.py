"""Interaction contract the agent core needs from a user interface.

Defined here (not in ``cli/``) so the agent depends on an abstraction and any
front-end — the terminal console, a test fake — can implement it
(dependency inversion).
"""

from __future__ import annotations

from typing import Any, Protocol


class AgentIO(Protocol):
    """What the harness, planner and supervisor need to talk to the user."""

    def confirm(self, question: str) -> bool:
        """Yes/no question; returns True on approval."""
        ...

    def ask(self, prompt: str) -> str:
        """Free-text question; returns the user's answer."""
        ...

    def show_plan(self, plan: str) -> None:
        """Display a proposed plan."""
        ...

    def show_tool_call(self, name: str, arguments: dict[str, Any]) -> None:
        """Display a tool invocation as it happens."""
        ...

    def show_tool_result(self, content: str, is_error: bool) -> None:
        """Display a summary of a tool result."""
        ...

    def detail(self, text: str) -> None:
        """Display low-importance progress information."""
        ...
