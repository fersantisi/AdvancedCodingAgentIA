"""Loop detection: notice when the agent repeats actions without progressing.

The harness records every executed tool call. When the same call keeps
producing the same result (e.g. re-running a failing command, re-reading an
unchanged file), the detector first asks the harness to inject a corrective
nudge into the conversation; if the repetition continues, it tells the
harness to abort the turn with a structured explanation of what was tried
and what is missing.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum

from coding_agent.models import ToolCall, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_WARN_AFTER = 2
DEFAULT_ABORT_AFTER = 4

NUDGE_MESSAGE = (
    "You are repeating the same action and obtaining the same result. "
    "Do not run it again. Change strategy: try a different tool or approach, "
    "re-plan the task, ask the user for help with the ask_user tool, or stop "
    "and explain what you tried, what information is missing and what you need to continue."
)


class LoopVerdict(StrEnum):
    OK = "ok"
    WARN = "warn"
    ABORT = "abort"


class LoopDetector:
    """Counts identical (tool call, result) repetitions within one turn."""

    def __init__(
        self,
        warn_after: int = DEFAULT_WARN_AFTER,
        abort_after: int = DEFAULT_ABORT_AFTER,
    ) -> None:
        if not 1 <= warn_after < abort_after:
            raise ValueError("expected 1 <= warn_after < abort_after")
        self._warn_after = warn_after
        self._abort_after = abort_after
        self._counts: dict[str, int] = {}
        self._warned: set[str] = set()
        self._recent: list[str] = []

    def reset(self) -> None:
        """Forget everything (called at the start of each turn)."""
        self._counts.clear()
        self._warned.clear()
        self._recent.clear()

    def record(self, call: ToolCall, result: ToolResult) -> LoopVerdict:
        """Register one executed call and judge whether the agent is looping."""
        fingerprint = self._fingerprint(call, result)
        count = self._counts.get(fingerprint, 0) + 1
        self._counts[fingerprint] = count
        self._recent.append(f"{call.name}({_compact(call.arguments)}) -> {_status(result)}")

        if count >= self._abort_after:
            logger.warning("Loop detected (abort): %s repeated %d times", call.name, count)
            return LoopVerdict.ABORT
        if count >= self._warn_after and fingerprint not in self._warned:
            self._warned.add(fingerprint)
            logger.warning("Loop detected (warn): %s repeated %d times", call.name, count)
            return LoopVerdict.WARN
        return LoopVerdict.OK

    def abort_summary(self) -> str:
        """Structured explanation for the user when a turn is aborted."""
        attempts = "\n".join(f"- {entry}" for entry in self._recent[-8:])
        return (
            "I stopped this turn because I was repeating the same actions without "
            "making progress (same tool call, same result).\n\n"
            f"What I tried (most recent actions):\n{attempts}\n\n"
            "I do not have enough evidence to continue on this path. Please tell me "
            "how to proceed, provide the missing information, or adjust the request."
        )

    @staticmethod
    def _fingerprint(call: ToolCall, result: ToolResult) -> str:
        arguments = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
        return f"{call.name}|{arguments}|{result.is_error}|{hash(result.content)}"


def _compact(arguments: dict) -> str:
    rendered = json.dumps(arguments, ensure_ascii=False, default=str)
    return rendered if len(rendered) <= 120 else rendered[:120] + "..."


def _status(result: ToolResult) -> str:
    return "error" if result.is_error else "ok"
