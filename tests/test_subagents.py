"""Tests for the subagent framework: specs, runner, delegate tool, orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.agent import SubAgentRunner, Supervisor, default_specs
from coding_agent.agent.subagent import SubAgentSpec
from coding_agent.config.guardrails import Guardrails
from coding_agent.config.policies import AgentPolicies
from coding_agent.models import AssistantTurn, TaskState, ToolCall
from coding_agent.observability.base import NullTracer
from coding_agent.tools import ToolError, ToolRegistry
from coding_agent.tools.delegate import DelegateTool
from tests.conftest import EchoTool, FakeIO, FakeLLMClient, make_harness

REQUIRED_SUBAGENTS = {"explorer", "researcher", "implementer", "tester", "reviewer"}


def make_runner(
    llm: FakeLLMClient,
    io: FakeIO,
    state: TaskState,
    specs: dict[str, SubAgentSpec] | None = None,
) -> SubAgentRunner:
    return SubAgentRunner(
        llm=llm,
        registry=ToolRegistry([EchoTool()]),
        guardrails=Guardrails.permissive(),
        policies=AgentPolicies.permissive(),
        supervisor=Supervisor(io, enabled=False),
        io=io,
        state=state,
        tracer=NullTracer(),
        working_dir=Path.cwd(),
        specs=specs,
        memory_text="remember: the project uses Laravel",
    )


class TestSpecs:
    def test_the_five_required_subagents_exist(self) -> None:
        specs = default_specs()
        assert set(specs) == REQUIRED_SUBAGENTS

    def test_permissions_differ_per_subagent(self) -> None:
        specs = default_specs()
        assert "write_file" in specs["implementer"].tool_names
        assert "write_file" not in specs["explorer"].tool_names
        assert "rag_search" in specs["researcher"].tool_names


class TestRegistrySubset:
    def test_subset_keeps_only_named_tools_and_skips_unknown(self) -> None:
        registry = ToolRegistry([EchoTool()])
        subset = registry.subset(("echo", "not_registered"))
        assert subset.names() == ("echo",)


class TestSubAgentRunner:
    def test_run_executes_tools_and_reports_into_state(self) -> None:
        call = ToolCall(id="1", name="echo", arguments={"text": "hola"})
        llm = FakeLLMClient(
            [AssistantTurn(text=None, tool_calls=(call,)), AssistantTurn(text="explorer report")]
        )
        state = TaskState()
        spec = SubAgentSpec(name="explorer", role="explores", mission="Explore.", tool_names=("echo",))
        runner = make_runner(llm, FakeIO(), state, specs={"explorer": spec})

        result = runner.run("explorer", "map the repository")

        assert result == "explorer report"
        assert state.subagent_reports[0].agent == "explorer"
        assert state.subagent_reports[0].summary == "explorer report"
        # fresh conversation: system prompt is the subagent prompt, with shared context
        system = llm.requests[0][0][0]
        assert "`explorer` subagent" in system.content
        assert "Current shared task state" in system.content
        assert "the project uses Laravel" in system.content
        # the subagent only saw its own tools
        assert [spec.name for spec in llm.requests[0][1]] == ["echo"]

    def test_unknown_agent_raises_key_error(self) -> None:
        runner = make_runner(FakeLLMClient([]), FakeIO(), TaskState())
        with pytest.raises(KeyError):
            runner.run("ghost", "do something")


class RecordingDispatch:
    def __init__(self, answer: str = "done") -> None:
        self.calls: list[tuple[str, str]] = []
        self._answer = answer

    def run(self, agent: str, task: str) -> str:
        self.calls.append((agent, task))
        return self._answer


class TestDelegateTool:
    def test_execute_dispatches_and_labels_the_report(self) -> None:
        dispatch = RecordingDispatch("all mapped")
        tool = DelegateTool(dispatch, {"explorer": "explores the repo"})
        output = tool.execute({"agent": "explorer", "task": "map it"})
        assert dispatch.calls == [("explorer", "map it")]
        assert output == "[explorer report]\nall mapped"

    def test_description_and_schema_list_the_agents(self) -> None:
        tool = DelegateTool(RecordingDispatch(), {"explorer": "explores", "tester": "tests"})
        assert "explorer" in tool.description
        assert sorted(tool.parameters["properties"]["agent"]["enum"]) == ["explorer", "tester"]

    def test_unknown_agent_raises_tool_error(self) -> None:
        tool = DelegateTool(RecordingDispatch(), {"explorer": "explores"})
        with pytest.raises(ToolError, match="Unknown subagent"):
            tool.execute({"agent": "ghost", "task": "x"})

    def test_delegate_is_read_only(self) -> None:
        assert DelegateTool(RecordingDispatch(), {"explorer": "x"}).read_only is True


class TestOrchestration:
    def test_main_agent_delegates_via_the_tool_and_finishes(self) -> None:
        dispatch = RecordingDispatch("repo mapped: it is Laravel")
        delegate = DelegateTool(dispatch, {"explorer": "explores the repo"})
        call = ToolCall(id="1", name="delegate", arguments={"agent": "explorer", "task": "map"})
        turns = [
            AssistantTurn(text=None, tool_calls=(call,)),
            AssistantTurn(text="The repo is a Laravel API."),
        ]
        io = FakeIO()
        harness, _, history = make_harness(turns, io, tools=[delegate])

        assert harness.run_turn("analyze the repo") == "The repo is a Laravel API."
        assert dispatch.calls == [("explorer", "map")]
        tool_message = history.messages()[3]
        assert "[explorer report]" in tool_message.content
