"""Retry decorator for LLM clients (transient failures only)."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.models import AssistantTurn, Message, ToolSpec

logger = logging.getLogger(__name__)


class RetryingLLMClient(LLMClient):
    """Wraps any ``LLMClient`` with exponential-backoff retries.

    Only errors flagged ``retryable`` (network, rate limit, 5xx) are retried;
    everything else propagates immediately.
    """

    def __init__(self, inner: LLMClient, max_attempts: int = 3, base_delay: float = 1.0) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._inner = inner
        self._max_attempts = max_attempts
        self._base_delay = base_delay

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> AssistantTurn:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._inner.complete(messages, tools)
            except LLMError as exc:
                if not exc.retryable or attempt == self._max_attempts:
                    raise
                delay = self._base_delay * 2 ** (attempt - 1)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    self._max_attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise AssertionError("unreachable")
