"""Langfuse observability backend.

The ONLY module that touches the ``langfuse`` SDK. It maps the provider-agnostic
:class:`~coding_agent.observability.base.Tracer` events onto Langfuse primitives:

* ``start_turn`` / ``end_turn``  -> one Langfuse **trace** per turn (named after
  the agent). Turns nest (main -> subagent), so active traces are kept on a stack
  and events attach to the innermost one.
* ``record_llm_call``            -> a **generation** (model, token usage, cost,
  latency; flagged as an error level when the call failed).
* ``record_tool_call``           -> a **span** (arguments in, output preview out).
* ``record_retrieval``           -> a **span** describing the RAG query and sources.

The SDK is imported lazily inside ``__init__`` so that (a) importing this module
never fails when ``langfuse`` is not installed and (b) tests can inject a fake
client and stay offline. Per the :class:`Tracer` contract, no method may raise:
every backend interaction is wrapped and downgraded to a ``logger.warning``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from coding_agent.config.settings import Settings
from coding_agent.models import Usage
from coding_agent.observability.base import Tracer

logger = logging.getLogger(__name__)


class LangfuseTracer(Tracer):
    """Sends turns, LLM calls, tool calls and retrievals to Langfuse."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if client is None:
            from langfuse import Langfuse  # lazy: keeps langfuse an optional dependency

            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        self._client = client
        # Stack of active traces; the innermost turn owns any events emitted.
        self._traces: list[Any] = []

    def start_turn(self, agent: str, user_input: str) -> None:
        try:
            trace = self._client.trace(name=agent, input=user_input)
            self._traces.append(trace)
        except Exception as exc:  # never break the agent loop
            logger.warning("Langfuse start_turn failed: %s", exc)

    def end_turn(self, agent: str, final_text: str, iterations: int) -> None:
        try:
            trace = self._traces.pop() if self._traces else None
            if trace is not None:
                trace.update(output=final_text, metadata={"iterations": iterations})
        except Exception as exc:
            logger.warning("Langfuse end_turn failed: %s", exc)

    def record_llm_call(
        self,
        *,
        model: str,
        message_count: int,
        latency_seconds: float,
        usage: Usage | None,
        cost_usd: float | None,
        tool_calls: Sequence[str],
        error: str | None = None,
    ) -> None:
        trace = self._current_trace()
        if trace is None:
            return
        try:
            usage_details = (
                {
                    "input": usage.prompt_tokens,
                    "output": usage.completion_tokens,
                    "total": usage.total_tokens,
                }
                if usage is not None
                else None
            )
            trace.generation(
                name="llm",
                model=model,
                usage_details=usage_details,
                metadata={
                    "message_count": message_count,
                    "latency_seconds": latency_seconds,
                    "cost_usd": cost_usd,
                    "tool_calls": list(tool_calls),
                },
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
        except Exception as exc:
            logger.warning("Langfuse record_llm_call failed: %s", exc)

    def record_tool_call(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        output_preview: str,
        is_error: bool,
        latency_seconds: float,
    ) -> None:
        trace = self._current_trace()
        if trace is None:
            return
        try:
            trace.span(
                name=name,
                input=dict(arguments),
                output=output_preview,
                level="ERROR" if is_error else "DEFAULT",
                metadata={"is_error": is_error, "latency_seconds": latency_seconds},
            )
        except Exception as exc:
            logger.warning("Langfuse record_tool_call failed: %s", exc)

    def record_retrieval(self, *, query: str, sources: Sequence[str]) -> None:
        trace = self._current_trace()
        if trace is None:
            return
        try:
            trace.span(name="rag_retrieval", input=query, output=list(sources))
        except Exception as exc:
            logger.warning("Langfuse record_retrieval failed: %s", exc)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:
            logger.warning("Langfuse flush failed: %s", exc)

    def _current_trace(self) -> Any | None:
        return self._traces[-1] if self._traces else None
