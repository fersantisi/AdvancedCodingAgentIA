"""Provider-agnostic tracing contract.

The harness, the tracing LLM decorator and the RAG tool emit events through
this interface. Concrete backends (Langfuse in ``langfuse_tracer.py``) live
behind it; :class:`NullTracer` keeps everything a no-op when observability is
not configured. This module has no external dependencies, so ``agent/`` may
import it (same rule as ``llm/base``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from coding_agent.models import Usage


class Tracer(ABC):
    """Contract every observability backend must fulfil.

    Implementations must never raise out of these methods: observability
    failures must not break the agent loop.
    """

    @abstractmethod
    def start_turn(self, agent: str, user_input: str) -> None:
        """A turn (one ``run_turn`` call) begins for the given agent."""

    @abstractmethod
    def end_turn(self, agent: str, final_text: str, iterations: int) -> None:
        """The turn finished with the given final answer and iteration count."""

    @abstractmethod
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
        """One LLM completion attempt (including failed ones)."""

    @abstractmethod
    def record_tool_call(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        output_preview: str,
        is_error: bool,
        latency_seconds: float,
    ) -> None:
        """One executed (or refused) tool call."""

    @abstractmethod
    def record_retrieval(self, *, query: str, sources: Sequence[str]) -> None:
        """One RAG retrieval: the query and the source of each returned fragment."""

    def flush(self) -> None:  # noqa: B027 — optional hook, no-op by default
        """Push any buffered events to the backend (called before exit)."""


class NullTracer(Tracer):
    """Tracer used when no observability backend is configured."""

    def start_turn(self, agent: str, user_input: str) -> None:
        pass

    def end_turn(self, agent: str, final_text: str, iterations: int) -> None:
        pass

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
        pass

    def record_tool_call(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        output_preview: str,
        is_error: bool,
        latency_seconds: float,
    ) -> None:
        pass

    def record_retrieval(self, *, query: str, sources: Sequence[str]) -> None:
        pass
