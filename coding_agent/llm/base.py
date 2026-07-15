"""Provider-agnostic LLM client contract.

The harness depends exclusively on this module; concrete providers
(OpenAI today, others tomorrow) live behind it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from coding_agent.models import AssistantTurn, Message, ToolSpec


class LLMError(Exception):
    """Raised when an LLM call fails.

    ``retryable`` marks transient failures (network, rate limits, 5xx)
    that a retry wrapper may attempt again.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMClient(ABC):
    """Contract every LLM provider implementation must fulfil."""

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> AssistantTurn:
        """Send the conversation to the model and return its next turn.

        Raises:
            LLMError: if the provider call fails.
        """
