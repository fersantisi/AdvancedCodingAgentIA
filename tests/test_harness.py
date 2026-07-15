"""Tests for the inner tool-execution loop (the harness)."""

from __future__ import annotations

import json

from coding_agent.config.guardrails import Guardrails
from coding_agent.models import AssistantTurn, Role, ToolCall
from tests.conftest import FakeIO, make_harness


def echo_call(call_id: str = "call_1", text: str = "hi") -> ToolCall:
    return ToolCall(id=call_id, name="echo", arguments={"text": text})


class TestInnerLoop:
    def test_plain_answer_needs_single_iteration(self, fake_io):
        harness, llm, _ = make_harness([AssistantTurn(text="just an answer")], fake_io)
        assert harness.run_turn("hello") == "just an answer"
        assert len(llm.requests) == 1

    def test_tool_call_then_final_answer(self, fake_io):
        turns = [
            AssistantTurn(text=None, tool_calls=(echo_call(),)),
            AssistantTurn(text="done"),
        ]
        harness, llm, history = make_harness(turns, fake_io)
        assert harness.run_turn("use echo") == "done"
        assert len(llm.requests) == 2
        tool_messages = [m for m in history.messages() if m.role is Role.TOOL]
        assert tool_messages[0].content == "echo: hi"

    def test_multiple_tool_calls_in_one_turn(self, fake_io):
        turns = [
            AssistantTurn(text=None, tool_calls=(echo_call("c1", "a"), echo_call("c2", "b"))),
            AssistantTurn(text="both done"),
        ]
        harness, _, history = make_harness(turns, fake_io)
        assert harness.run_turn("go") == "both done"
        tool_messages = [m for m in history.messages() if m.role is Role.TOOL]
        assert [m.content for m in tool_messages] == ["echo: a", "echo: b"]

    def test_unknown_tool_becomes_error_result(self, fake_io):
        turns = [
            AssistantTurn(text=None, tool_calls=(ToolCall(id="c1", name="ghost", arguments={}),)),
            AssistantTurn(text="recovered"),
        ]
        harness, _, history = make_harness(turns, fake_io)
        assert harness.run_turn("go") == "recovered"
        tool_message = next(m for m in history.messages() if m.role is Role.TOOL)
        assert "ERROR" in tool_message.content
        assert "Unknown tool" in tool_message.content

    def test_max_iterations_cap(self, fake_io):
        endless = [AssistantTurn(text=None, tool_calls=(echo_call(f"c{i}"),)) for i in range(5)]
        harness, _, _ = make_harness(endless, fake_io, max_iterations=3)
        assert "Stopped after 3" in harness.run_turn("loop forever")

    def test_history_persists_across_turns(self, fake_io):
        harness, llm, history = make_harness(
            [AssistantTurn(text="first"), AssistantTurn(text="second")], fake_io
        )
        harness.run_turn("turn one")
        harness.run_turn("turn two")
        # second request must include the whole first turn
        second_request_messages = llm.requests[1][0]
        contents = [m.content for m in second_request_messages]
        assert "turn one" in contents
        assert "first" in contents
        assert len(history) == 5  # system + 2 user + 2 assistant


class TestSupervision:
    def test_denied_mutating_tool_returns_error_result(self):
        io = FakeIO(confirm_answers=[False])
        turns = [
            AssistantTurn(text=None, tool_calls=(echo_call(),)),
            AssistantTurn(text="adapted"),
        ]
        harness, _, history = make_harness(turns, io, supervision_enabled=True)
        assert harness.run_turn("go") == "adapted"
        tool_message = next(m for m in history.messages() if m.role is Role.TOOL)
        assert "Denied by the user" in tool_message.content
        assert len(io.confirm_questions) == 1

    def test_approved_mutating_tool_runs(self):
        io = FakeIO(confirm_answers=[True])
        turns = [
            AssistantTurn(text=None, tool_calls=(echo_call(),)),
            AssistantTurn(text="ok"),
        ]
        harness, _, history = make_harness(turns, io, supervision_enabled=True)
        harness.run_turn("go")
        tool_message = next(m for m in history.messages() if m.role is Role.TOOL)
        assert tool_message.content == "echo: hi"

    def test_supervision_disabled_never_asks(self):
        io = FakeIO(confirm_answers=[])
        turns = [
            AssistantTurn(text=None, tool_calls=(echo_call(),)),
            AssistantTurn(text="ok"),
        ]
        harness, _, _ = make_harness(turns, io, supervision_enabled=False)
        harness.run_turn("go")
        assert io.confirm_questions == []


class TestGuardrailsIntegration:
    def test_blocked_call_becomes_error_result(self, fake_io, tmp_path):
        guardrails = Guardrails(allowed_directories=(tmp_path.resolve(),))
        outside = str(tmp_path.parent / "outside.txt")
        turns = [
            AssistantTurn(
                text=None,
                tool_calls=(ToolCall(id="c1", name="echo", arguments={"path": outside, "text": "x"}),),
            ),
            AssistantTurn(text="understood"),
        ]
        harness, _, history = make_harness(turns, fake_io, guardrails=guardrails)
        assert harness.run_turn("go") == "understood"
        tool_message = next(m for m in history.messages() if m.role is Role.TOOL)
        assert "Blocked by guardrails" in tool_message.content
