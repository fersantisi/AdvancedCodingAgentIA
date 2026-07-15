"""Provider-neutral conversation messages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coding_agent.models.tool_call import ToolCall


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class Message:
    """A single conversation message.

    ``tool_calls`` is only populated for assistant messages that request tools;
    ``tool_call_id`` is only populated for tool-result messages.
    """

    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
