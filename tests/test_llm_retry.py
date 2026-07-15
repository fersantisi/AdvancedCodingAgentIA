"""Tests for the retry wrapper around LLM clients."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.llm.retry import RetryingLLMClient
from coding_agent.models import AssistantTurn, Message, ToolSpec


class FlakyLLM(LLMClient):
    def __init__(self, failures: int, retryable: bool = True) -> None:
        self._failures = failures
        self._retryable = retryable
        self.calls = 0

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AssistantTurn:
        self.calls += 1
        if self.calls <= self._failures:
            raise LLMError("transient boom", retryable=self._retryable)
        return AssistantTurn(text="ok")


class TestRetryingLLMClient:
    def test_retries_transient_errors(self):
        inner = FlakyLLM(failures=2)
        client = RetryingLLMClient(inner, max_attempts=3, base_delay=0)
        assert client.complete([]).text == "ok"
        assert inner.calls == 3

    def test_gives_up_after_max_attempts(self):
        inner = FlakyLLM(failures=5)
        client = RetryingLLMClient(inner, max_attempts=2, base_delay=0)
        with pytest.raises(LLMError):
            client.complete([])
        assert inner.calls == 2

    def test_non_retryable_error_fails_immediately(self):
        inner = FlakyLLM(failures=1, retryable=False)
        client = RetryingLLMClient(inner, max_attempts=3, base_delay=0)
        with pytest.raises(LLMError):
            client.complete([])
        assert inner.calls == 1
