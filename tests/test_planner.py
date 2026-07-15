"""Tests for plan mode: approve, modify and reject flows."""

from __future__ import annotations

from coding_agent.agent import ConversationHistory, Planner
from coding_agent.agent.harness import PLAN_REJECTED_MESSAGE
from coding_agent.models import AssistantTurn
from tests.conftest import FakeIO, FakeLLMClient, make_harness


def make_planner(plans: list[str], io: FakeIO) -> tuple[Planner, ConversationHistory]:
    llm = FakeLLMClient([AssistantTurn(text=plan) for plan in plans])
    history = ConversationHistory("system")
    history.add_user("do the task")
    return Planner(llm, io, enabled=True), history


class TestPlanNegotiation:
    def test_approve_appends_plan_and_returns_true(self):
        io = FakeIO(ask_answers=["a"])
        planner, history = make_planner(["1. step one\n2. step two"], io)
        assert planner.negotiate(history) is True
        contents = [m.content for m in history.messages()]
        assert any("step one" in c for c in contents)
        assert any("approved" in c.lower() for c in contents)
        assert io.plans == ["1. step one\n2. step two"]

    def test_reject_returns_false_and_records_rejection(self):
        io = FakeIO(ask_answers=["r"])
        planner, history = make_planner(["1. dangerous step"], io)
        assert planner.negotiate(history) is False
        contents = [m.content for m in history.messages()]
        assert any("rejected" in c.lower() for c in contents)

    def test_modify_regenerates_with_feedback(self):
        io = FakeIO(ask_answers=["m", "use fewer steps", "a"])
        planner, history = make_planner(["1. v1 plan", "1. v2 plan"], io)
        assert planner.negotiate(history) is True
        assert io.plans == ["1. v1 plan", "1. v2 plan"]
        contents = [m.content for m in history.messages()]
        assert any("v2 plan" in c for c in contents)

    def test_invalid_choice_is_reprompted(self):
        io = FakeIO(ask_answers=["x", "a"])
        planner, history = make_planner(["1. plan"], io)
        assert planner.negotiate(history) is True


class TestPlanModeInHarness:
    def test_rejected_plan_executes_nothing(self):
        io = FakeIO(ask_answers=["r"])
        # only ONE scripted turn: the plan; execution would exhaust the fake
        harness, llm, _ = make_harness([AssistantTurn(text="1. plan")], io, plan_enabled=True)
        assert harness.run_turn("task") == PLAN_REJECTED_MESSAGE
        assert len(llm.requests) == 1  # planning call only
        assert io.tool_calls == []

    def test_plan_disabled_skips_negotiation(self, fake_io):
        harness, llm, _ = make_harness([AssistantTurn(text="direct")], fake_io, plan_enabled=False)
        assert harness.run_turn("task") == "direct"
        assert fake_io.plans == []

    def test_planning_call_offers_no_tools(self):
        io = FakeIO(ask_answers=["a"])
        turns = [AssistantTurn(text="1. plan"), AssistantTurn(text="done")]
        harness, llm, _ = make_harness(turns, io, plan_enabled=True)
        harness.run_turn("task")
        planning_request_tools = llm.requests[0][1]
        execution_request_tools = llm.requests[1][1]
        assert planning_request_tools == ()
        assert len(execution_request_tools) > 0
