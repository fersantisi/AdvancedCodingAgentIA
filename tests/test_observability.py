"""Tests for the observability seam: tracing client, pricing, factory, harness spans."""

from __future__ import annotations

import dataclasses

import pytest

from coding_agent.config.settings import Settings, SettingsError
from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.models import AssistantTurn, ToolCall, Usage
from coding_agent.observability import NullTracer, TracingLLMClient, create_tracer
from coding_agent.observability.pricing import estimate_cost_usd
from tests.conftest import FakeIO, FakeLLMClient, FakeTracer, make_harness


class FailingLLM(LLMClient):
    def complete(self, messages, tools=()):  # type: ignore[override]
        raise LLMError("boom", retryable=False)


class TestPricing:
    def test_known_model_estimates_cost(self) -> None:
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert estimate_cost_usd("gpt-4o-mini", usage) == pytest.approx(0.75)

    def test_unknown_model_or_missing_usage_returns_none(self) -> None:
        assert estimate_cost_usd("mystery-model", Usage(1, 1)) is None
        assert estimate_cost_usd("gpt-4o-mini", None) is None


class TestTracingLLMClient:
    def test_records_success_with_usage_cost_and_tools(self) -> None:
        call = ToolCall(id="1", name="echo", arguments={})
        turn = AssistantTurn(text=None, tool_calls=(call,), usage=Usage(100, 50))
        tracer = FakeTracer()
        client = TracingLLMClient(FakeLLMClient([turn]), tracer, model="gpt-4o-mini")

        result = client.complete((), ())

        assert result is turn
        recorded = tracer.llm_calls[0]
        assert recorded["model"] == "gpt-4o-mini"
        assert recorded["usage"] == Usage(100, 50)
        assert recorded["cost_usd"] > 0
        assert recorded["tool_calls"] == ("echo",)
        assert recorded["latency_seconds"] >= 0
        assert recorded["error"] is None

    def test_records_failures_and_reraises(self) -> None:
        tracer = FakeTracer()
        client = TracingLLMClient(FailingLLM(), tracer, model="gpt-4o-mini")
        with pytest.raises(LLMError, match="boom"):
            client.complete((), ())
        assert tracer.llm_calls[0]["error"] == "boom"
        assert tracer.llm_calls[0]["usage"] is None


class TestHarnessTracing:
    def test_turn_and_tool_spans_are_recorded(self) -> None:
        call = ToolCall(id="1", name="echo", arguments={"text": "hi"})
        turns = [AssistantTurn(text=None, tool_calls=(call,)), AssistantTurn(text="done")]
        tracer = FakeTracer()
        harness, _, _ = make_harness(turns, FakeIO(), tracer=tracer)

        harness.run_turn("do it")

        assert tracer.turns_started == [("main", "do it")]
        assert tracer.turns_ended == [("main", "done", 2)]
        recorded = tracer.tool_calls[0]
        assert recorded["name"] == "echo"
        assert recorded["is_error"] is False
        assert "echo: hi" in recorded["output_preview"]

    def test_error_tool_calls_are_recorded_as_errors(self) -> None:
        call = ToolCall(id="1", name="ghost_tool", arguments={})
        turns = [AssistantTurn(text=None, tool_calls=(call,)), AssistantTurn(text="done")]
        tracer = FakeTracer()
        harness, _, _ = make_harness(turns, FakeIO(), tracer=tracer)

        harness.run_turn("do it")
        assert tracer.tool_calls[0]["is_error"] is True


class TestFactory:
    def test_none_provider_returns_null_tracer(self) -> None:
        settings = Settings(openai_api_key="key")
        assert isinstance(create_tracer(settings), NullTracer)

    def test_unknown_provider_raises(self) -> None:
        settings = dataclasses.replace(
            Settings(openai_api_key="key"), observability_provider="mystery"
        )
        with pytest.raises(SettingsError, match="mystery"):
            create_tracer(settings)
