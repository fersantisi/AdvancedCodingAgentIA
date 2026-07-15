"""Context compaction: keep long sessions within a bounded context size.

When the history grows past a threshold, the oldest span (everything between
the system prompt and the recent tail) is summarized with a tool-free LLM
call and replaced by a single summary message. Decisions, modified files and
unresolved issues are explicitly preserved; the recent tail is never touched,
and the split point never separates an assistant tool request from its tool
results.
"""

from __future__ import annotations

import logging

from coding_agent.agent.conversation import ConversationHistory
from coding_agent.llm import LLMClient
from coding_agent.models import Message, Role

logger = logging.getLogger(__name__)

DEFAULT_KEEP_RECENT = 12

SUMMARY_INSTRUCTION = (
    "Summarize the conversation above for your own future reference. Preserve: "
    "the user's goals, decisions taken and their reasons, files read or modified, "
    "commands run with their outcomes, errors found, and any unresolved issue. "
    "Be concise (bullet points). Respond with the summary only."
)

SUMMARY_PREFIX = "Summary of the earlier conversation (compacted to save context):"


class ContextCompactor:
    """Summarizes old history in place once it exceeds ``max_messages``."""

    def __init__(
        self,
        llm: LLMClient,
        max_messages: int = 60,
        keep_recent: int = DEFAULT_KEEP_RECENT,
    ) -> None:
        if keep_recent < 2 or max_messages <= keep_recent:
            raise ValueError("expected max_messages > keep_recent >= 2")
        self._llm = llm
        self._max_messages = max_messages
        self._keep_recent = keep_recent

    def compact_if_needed(self, history: ConversationHistory) -> bool:
        """Compact the history when it is too long. Returns True if it did."""
        messages = history.messages()
        if len(messages) <= self._max_messages:
            return False

        split = _safe_split_index(messages, len(messages) - self._keep_recent)
        if split <= 1:
            return False

        summary = self._summarize(messages[:split])
        history.replace_span(1, split, f"{SUMMARY_PREFIX}\n{summary}")
        logger.info(
            "Compacted history: %d messages summarized, %d kept",
            split - 1,
            len(history),
        )
        return True

    def _summarize(self, messages: tuple[Message, ...]) -> str:
        request = tuple(messages) + (
            Message(role=Role.USER, content=SUMMARY_INSTRUCTION),
        )
        turn = self._llm.complete(request)
        return turn.text or "(no summary produced)"


def _safe_split_index(messages: tuple[Message, ...], target: int) -> int:
    """Latest index <= target where the tail starts at a USER message.

    Splitting at a USER message guarantees no assistant tool request is
    separated from its tool results.
    """
    for index in range(min(target, len(messages) - 1), 1, -1):
        if messages[index].role is Role.USER:
            return index
    return 0
