"""Tests for the Langfuse observability backend.

Fully offline: a fake Langfuse client is injected (constructor DI) or a fake
``langfuse`` module is registered in ``sys.modules`` so the lazy import in the
factory path resolves without the real SDK or any network.
"""

from __future__ import annotations

import sys
import types

import pytest

from coding_agent.config.settings import Settings, SettingsError
from coding_agent.models import Usage
from coding_agent.observability import create_tracer
from coding_agent.observability.langfuse_tracer import LangfuseTracer


class RecordingTrace:
    """Fake Langfuse trace that records every generation/span/update."""

    def __init__(self, name: str | None, input_: object) -> None:
        self.name = name
        self.input = input_
        self.generations: list[dict] = []
        self.spans: list[dict] = []
        self.updates: list[dict] = []

    def generation(self, **kwargs) -> None:
        self.generations.append(kwargs)

    def span(self, **kwargs) -> None:
        self.spans.append(kwargs)

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class RecordingLangfuseClient:
    """Fake Langfuse client capturing init kwargs, traces and flushes."""

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.traces: list[RecordingTrace] = []
        self.flush_count = 0

    def trace(self, **kwargs) -> RecordingTrace:
        trace = RecordingTrace(kwargs.get("name"), kwargs.get("input"))
        self.traces.append(trace)
        return trace

    def flush(self) -> None:
        self.flush_count += 1


class _BrokenTrace:
    def generation(self, **kwargs) -> None:
        raise RuntimeError("generation down")

    def span(self, **kwargs) -> None:
        raise RuntimeError("span down")

    def update(self, **kwargs) -> None:
        raise RuntimeError("update down")


class _BrokenClient:
    def trace(self, **kwargs) -> _BrokenTrace:
        return _BrokenTrace()

    def flush(self) -> None:
        raise RuntimeError("flush down")


def _settings() -> Settings:
    return Settings(
        openai_api_key="key",
        observability_provider="langfuse",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )


class TestBehavior:
    def test_turn_creates_and_finishes_a_trace(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("main", "analyze repo")
        tracer.end_turn("main", "done", iterations=3)

        assert len(client.traces) == 1
        trace = client.traces[0]
        assert trace.name == "main"
        assert trace.input == "analyze repo"
        assert trace.updates[0]["output"] == "done"
        assert trace.updates[0]["metadata"]["iterations"] == 3

    def test_llm_call_becomes_a_generation_with_usage_and_cost(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("main", "in")
        tracer.record_llm_call(
            model="gpt-4o-mini",
            message_count=4,
            latency_seconds=0.5,
            usage=Usage(100, 50),
            cost_usd=0.001,
            tool_calls=["read_file"],
        )

        gen = client.traces[0].generations[0]
        assert gen["model"] == "gpt-4o-mini"
        assert gen["usage_details"] == {"input": 100, "output": 50, "total": 150}
        assert gen["metadata"]["cost_usd"] == 0.001
        assert gen["metadata"]["tool_calls"] == ["read_file"]
        assert gen["level"] == "DEFAULT"

    def test_failed_llm_call_is_flagged_as_error(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("main", "in")
        tracer.record_llm_call(
            model="gpt-4o-mini",
            message_count=1,
            latency_seconds=0.1,
            usage=None,
            cost_usd=None,
            tool_calls=[],
            error="boom",
        )

        gen = client.traces[0].generations[0]
        assert gen["level"] == "ERROR"
        assert gen["status_message"] == "boom"
        assert gen["usage_details"] is None

    def test_tool_call_becomes_a_span(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("main", "in")
        tracer.record_tool_call(
            name="read_file",
            arguments={"path": "x.php"},
            output_preview="contents",
            is_error=False,
            latency_seconds=0.2,
        )

        span = client.traces[0].spans[0]
        assert span["name"] == "read_file"
        assert span["input"] == {"path": "x.php"}
        assert span["output"] == "contents"
        assert span["metadata"]["is_error"] is False

    def test_retrieval_becomes_a_span_with_sources(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("researcher", "in")
        tracer.record_retrieval(query="routing", sources=["routing.md#chunk0"])

        span = client.traces[0].spans[0]
        assert span["name"] == "rag_retrieval"
        assert span["input"] == "routing"
        assert span["output"] == ["routing.md#chunk0"]

    def test_nested_turns_attach_events_to_innermost_trace(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)

        tracer.start_turn("main", "outer")
        tracer.start_turn("explorer", "inner")
        tracer.record_tool_call(
            name="list_files",
            arguments={},
            output_preview="ok",
            is_error=False,
            latency_seconds=0.1,
        )
        tracer.end_turn("explorer", "sub done", iterations=1)
        tracer.end_turn("main", "done", iterations=2)

        main_trace, explorer_trace = client.traces
        assert explorer_trace.name == "explorer"
        assert len(explorer_trace.spans) == 1  # inner event went to the inner trace
        assert main_trace.spans == []

    def test_flush_flushes_the_client(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)
        tracer.flush()
        assert client.flush_count == 1

    def test_events_without_active_trace_are_no_ops(self) -> None:
        client = RecordingLangfuseClient()
        tracer = LangfuseTracer(_settings(), client=client)
        # No start_turn: these must not raise and must not create traces.
        tracer.record_tool_call(
            name="t", arguments={}, output_preview="", is_error=False, latency_seconds=0.0
        )
        tracer.end_turn("main", "x", iterations=0)
        assert client.traces == []


class TestNeverRaises:
    def test_backend_exceptions_are_swallowed(self) -> None:
        tracer = LangfuseTracer(_settings(), client=_BrokenClient())
        # None of these may propagate, per the Tracer contract.
        tracer.start_turn("main", "in")
        tracer.record_llm_call(
            model="m",
            message_count=1,
            latency_seconds=0.0,
            usage=Usage(1, 1),
            cost_usd=0.0,
            tool_calls=[],
        )
        tracer.record_tool_call(
            name="t", arguments={}, output_preview="", is_error=True, latency_seconds=0.0
        )
        tracer.record_retrieval(query="q", sources=["s"])
        tracer.end_turn("main", "out", iterations=1)
        tracer.flush()


class TestFactory:
    def test_factory_selects_langfuse_when_configured(self, monkeypatch) -> None:
        captured: dict = {}

        def fake_ctor(**kwargs):
            captured.update(kwargs)
            return RecordingLangfuseClient(**kwargs)

        fake_module = types.ModuleType("langfuse")
        fake_module.Langfuse = fake_ctor  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langfuse", fake_module)

        tracer = create_tracer(_settings())

        assert isinstance(tracer, LangfuseTracer)
        assert captured == {"public_key": "pk", "secret_key": "sk", "host": _settings().langfuse_host}

    def test_validate_requires_keys_for_langfuse(self) -> None:
        settings = Settings(openai_api_key="key", observability_provider="langfuse")
        with pytest.raises(SettingsError, match="LANGFUSE_PUBLIC_KEY"):
            settings.validate()

    def test_validate_passes_with_keys(self) -> None:
        _settings().validate()  # must not raise


class TestHostFromEnv:
    def test_langfuse_host_env_wins(self, monkeypatch) -> None:
        monkeypatch.setenv("LANGFUSE_HOST", "https://eu.example.com")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.example.com")
        assert Settings.from_env(env_file=None).langfuse_host == "https://eu.example.com"

    def test_base_url_alias_used_when_host_absent(self, monkeypatch) -> None:
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
        assert Settings.from_env(env_file=None).langfuse_host == "https://us.cloud.langfuse.com"

    def test_default_host_when_neither_set(self, monkeypatch) -> None:
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        assert Settings.from_env(env_file=None).langfuse_host == "https://cloud.langfuse.com"
