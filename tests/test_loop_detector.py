"""Tests for loop detection and the ask_user tool."""

from __future__ import annotations

import pytest

from coding_agent.agent.loop_detector import NUDGE_MESSAGE, LoopDetector, LoopVerdict
from coding_agent.models import AssistantTurn, Role, TaskState, ToolCall, ToolResult
from coding_agent.tools import ToolError
from coding_agent.tools.ask_user import AskUserTool
from tests.conftest import FakeIO, make_harness


def call_and_result(text: str = "same") -> tuple[ToolCall, ToolResult]:
    call = ToolCall(id="1", name="echo", arguments={"text": text})
    return call, ToolResult(tool_call_id="1", content=f"echo: {text}")


class TestLoopDetector:
    def test_warns_then_aborts_on_identical_repetition(self) -> None:
        detector = LoopDetector(warn_after=2, abort_after=4)
        call, result = call_and_result()
        assert detector.record(call, result) is LoopVerdict.OK
        assert detector.record(call, result) is LoopVerdict.WARN
        assert detector.record(call, result) is LoopVerdict.OK  # warned only once
        assert detector.record(call, result) is LoopVerdict.ABORT

    def test_different_arguments_do_not_trip_it(self) -> None:
        detector = LoopDetector(warn_after=2, abort_after=4)
        for index in range(6):
            call, result = call_and_result(f"text {index}")
            assert detector.record(call, result) is LoopVerdict.OK

    def test_same_call_with_new_result_is_progress(self) -> None:
        detector = LoopDetector(warn_after=2, abort_after=4)
        call = ToolCall(id="1", name="run_command", arguments={"command": "pytest"})
        first = ToolResult(tool_call_id="1", content="1 failed")
        second = ToolResult(tool_call_id="1", content="all passed")
        assert detector.record(call, first) is LoopVerdict.OK
        assert detector.record(call, second) is LoopVerdict.OK

    def test_reset_forgets_previous_turn(self) -> None:
        detector = LoopDetector(warn_after=2, abort_after=4)
        call, result = call_and_result()
        detector.record(call, result)
        detector.reset()
        assert detector.record(call, result) is LoopVerdict.OK

    def test_abort_summary_explains_what_was_tried(self) -> None:
        detector = LoopDetector(warn_after=2, abort_after=3)
        call, result = call_and_result()
        for _ in range(3):
            detector.record(call, result)
        summary = detector.abort_summary()
        assert "repeating the same actions" in summary
        assert "echo" in summary
        assert "tell me how to proceed" in summary.lower()

    def test_invalid_thresholds_raise(self) -> None:
        with pytest.raises(ValueError):
            LoopDetector(warn_after=3, abort_after=3)


class TestHarnessIntegration:
    def test_nudge_is_injected_after_repeated_calls(self) -> None:
        call = ToolCall(id="1", name="echo", arguments={"text": "same"})
        turns = [
            AssistantTurn(text=None, tool_calls=(call,)),
            AssistantTurn(text=None, tool_calls=(call,)),
            AssistantTurn(text="I will change my approach."),
        ]
        detector = LoopDetector(warn_after=2, abort_after=4)
        harness, _, history = make_harness(turns, FakeIO(), loop_detector=detector)

        assert harness.run_turn("do it") == "I will change my approach."
        nudges = [
            message
            for message in history.messages()
            if message.role is Role.USER and message.content == NUDGE_MESSAGE
        ]
        assert len(nudges) == 1

    def test_persistent_loop_aborts_the_turn_with_an_explanation(self) -> None:
        call = ToolCall(id="1", name="echo", arguments={"text": "same"})
        turns = [AssistantTurn(text=None, tool_calls=(call,)) for _ in range(4)]
        detector = LoopDetector(warn_after=2, abort_after=4)
        state = TaskState()
        harness, llm, _ = make_harness(turns, FakeIO(), loop_detector=detector, state=state)

        result = harness.run_turn("do it")

        assert "repeating the same actions" in result
        assert len(llm.requests) == 4, "all scripted turns consumed, none after the abort"
        assert any("loop" in note for note in state.observations)


class TestAskUserTool:
    def test_returns_the_user_answer(self) -> None:
        io = FakeIO(ask_answers=["use the staging database"])
        tool = AskUserTool(io)
        output = tool.execute({"question": "Which database should I use?"})
        assert output == "User answered: use the staging database"

    def test_empty_answer_is_reported(self) -> None:
        io = FakeIO(ask_answers=[""])
        output = AskUserTool(io).execute({"question": "Anything?"})
        assert "did not answer" in output

    def test_missing_question_is_a_tool_error(self) -> None:
        with pytest.raises(ToolError):
            AskUserTool(FakeIO()).execute({})
