"""Conversation history: the full message list, kept for the whole session."""

from __future__ import annotations

from coding_agent.models import AssistantTurn, Message, Role, ToolResult


class ConversationHistory:
    """Message history shared by every turn until the program exits.

    Append-only, with one deliberate exception: :meth:`replace_span` lets the
    context compactor replace an old span with a summary message.
    """

    def __init__(self, system_prompt: str) -> None:
        self._messages: list[Message] = [Message(role=Role.SYSTEM, content=system_prompt)]

    def add_user(self, content: str) -> None:
        self._messages.append(Message(role=Role.USER, content=content))

    def add_assistant(self, turn: AssistantTurn) -> None:
        self._messages.append(
            Message(role=Role.ASSISTANT, content=turn.text or "", tool_calls=turn.tool_calls)
        )

    def add_assistant_text(self, content: str) -> None:
        self._messages.append(Message(role=Role.ASSISTANT, content=content))

    def add_tool_result(self, result: ToolResult) -> None:
        content = result.content if not result.is_error else f"ERROR: {result.content}"
        self._messages.append(
            Message(role=Role.TOOL, content=content, tool_call_id=result.tool_call_id)
        )

    def replace_span(self, start: int, end: int, summary: str) -> None:
        """Replace ``messages[start:end]`` with a single summary message.

        Used only by context compaction; ``start`` must be >= 1 so the system
        prompt is never removed.
        """
        if start < 1 or end <= start or end > len(self._messages):
            raise ValueError(f"Invalid compaction span [{start}:{end}] for {len(self._messages)} messages")
        self._messages[start:end] = [Message(role=Role.USER, content=summary)]

    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def __len__(self) -> int:
        return len(self._messages)
