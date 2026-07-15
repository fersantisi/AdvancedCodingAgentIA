"""Shared test doubles: fake LLM, fake IO, fake search provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from coding_agent.agent import AgentHarness, ConversationHistory, Planner, Supervisor
from coding_agent.config.guardrails import Guardrails
from coding_agent.llm.base import LLMClient
from coding_agent.models import AssistantTurn, Message, ToolSpec
from coding_agent.tools import Tool, ToolRegistry
from coding_agent.tools.web_search.provider import SearchProvider, SearchResult


class FakeLLMClient(LLMClient):
    """Returns scripted turns in order and records every request."""

    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)
        self.requests: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AssistantTurn:
        self.requests.append((tuple(messages), tuple(tools)))
        if not self._turns:
            raise AssertionError("FakeLLMClient ran out of scripted turns")
        return self._turns.pop(0)


class FakeIO:
    """Implements AgentIO; scripted answers, records everything shown."""

    def __init__(
        self,
        confirm_answers: list[bool] | None = None,
        ask_answers: list[str] | None = None,
    ) -> None:
        self.confirm_answers = list(confirm_answers or [])
        self.ask_answers = list(ask_answers or [])
        self.confirm_questions: list[str] = []
        self.plans: list[str] = []
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.tool_results: list[tuple[str, bool]] = []
        self.details: list[str] = []

    def confirm(self, question: str) -> bool:
        self.confirm_questions.append(question)
        return self.confirm_answers.pop(0) if self.confirm_answers else True

    def ask(self, prompt: str) -> str:
        return self.ask_answers.pop(0) if self.ask_answers else "a"

    def show_plan(self, plan: str) -> None:
        self.plans.append(plan)

    def show_tool_call(self, name: str, arguments: dict[str, Any]) -> None:
        self.tool_calls.append((name, arguments))

    def show_tool_result(self, content: str, is_error: bool) -> None:
        self.tool_results.append((content, is_error))

    def detail(self, text: str) -> None:
        self.details.append(text)


class EchoTool(Tool):
    """Trivial mutating tool for harness tests."""

    name = "echo"
    description = "Echo the given text."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    read_only = False

    def execute(self, arguments: dict[str, Any]) -> str:
        return f"echo: {arguments.get('text', '')}"


class FakeSearchProvider(SearchProvider):
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        return self._results[:max_results]


@pytest.fixture
def fake_io() -> FakeIO:
    return FakeIO()


def make_harness(
    turns: list[AssistantTurn],
    io: FakeIO,
    tools: list[Tool] | None = None,
    guardrails: Guardrails | None = None,
    supervision_enabled: bool = False,
    plan_enabled: bool = False,
    max_iterations: int = 10,
) -> tuple[AgentHarness, FakeLLMClient, ConversationHistory]:
    llm = FakeLLMClient(turns)
    history = ConversationHistory("test system prompt")
    harness = AgentHarness(
        llm=llm,
        registry=ToolRegistry(tools if tools is not None else [EchoTool()]),
        history=history,
        guardrails=guardrails or Guardrails.permissive(),
        supervisor=Supervisor(io, enabled=supervision_enabled),
        planner=Planner(llm, io, enabled=plan_enabled),
        io=io,
        max_iterations=max_iterations,
    )
    return harness, llm, history
