"""Models describing tool invocations, their results and assistant turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """A request by the LLM to execute one tool with parsed arguments."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """The outcome of executing (or refusing to execute) a tool call."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Provider-neutral description of a tool, exposed to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """Token accounting for one LLM call (used for observability)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class AssistantTurn:
    """One LLM response: optional text plus zero or more tool calls."""

    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage | None = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)
