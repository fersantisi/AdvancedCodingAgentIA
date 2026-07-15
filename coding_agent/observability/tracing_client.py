"""Tracing decorator for LLM clients (mirrors ``llm/retry.py``).

Wraps any ``LLMClient`` and reports every completion attempt — latency,
token usage, estimated cost, requested tool calls and errors — to a
:class:`Tracer`. Composed inside ``create_llm_client`` so retries are traced
per attempt.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.models import AssistantTurn, Message, ToolSpec
from coding_agent.observability.base import Tracer
from coding_agent.observability.pricing import estimate_cost_usd


class TracingLLMClient(LLMClient):
    """Records every LLM call through the configured tracer."""

    def __init__(self, inner: LLMClient, tracer: Tracer, model: str) -> None:
        self._inner = inner
        self._tracer = tracer
        self._model = model

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> AssistantTurn:
        started = time.monotonic()
        try:
            turn = self._inner.complete(messages, tools)
        except LLMError as exc:
            self._tracer.record_llm_call(
                model=self._model,
                message_count=len(messages),
                latency_seconds=time.monotonic() - started,
                usage=None,
                cost_usd=None,
                tool_calls=(),
                error=str(exc),
            )
            raise
        self._tracer.record_llm_call(
            model=self._model,
            message_count=len(messages),
            latency_seconds=time.monotonic() - started,
            usage=turn.usage,
            cost_usd=estimate_cost_usd(self._model, turn.usage),
            tool_calls=[call.name for call in turn.tool_calls],
        )
        return turn
