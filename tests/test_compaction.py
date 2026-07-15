"""Tests for context compaction and the history replace_span extension."""

from __future__ import annotations

import pytest

from coding_agent.agent import ConversationHistory
from coding_agent.agent.compaction import SUMMARY_PREFIX, ContextCompactor
from coding_agent.models import AssistantTurn, Message, Role, ToolCall, ToolResult
from tests.conftest import FakeLLMClient


def build_history(pairs: int) -> ConversationHistory:
    history = ConversationHistory("system prompt")
    for index in range(pairs):
        history.add_user(f"question {index}")
        history.add_assistant_text(f"answer {index}")
    return history


class TestReplaceSpan:
    def test_replaces_the_span_with_one_user_message(self) -> None:
        history = build_history(3)
        history.replace_span(1, 5, "summary here")
        messages = history.messages()
        assert len(messages) == 4  # system + summary + last pair
        assert messages[1].role is Role.USER
        assert messages[1].content == "summary here"
        assert messages[-1].content == "answer 2"

    def test_never_touches_the_system_prompt(self) -> None:
        history = build_history(2)
        with pytest.raises(ValueError):
            history.replace_span(0, 3, "summary")

    def test_rejects_invalid_spans(self) -> None:
        history = build_history(2)
        with pytest.raises(ValueError):
            history.replace_span(3, 3, "summary")
        with pytest.raises(ValueError):
            history.replace_span(1, 99, "summary")


class TestContextCompactor:
    def test_does_nothing_under_the_threshold(self) -> None:
        llm = FakeLLMClient([])  # would raise if called
        compactor = ContextCompactor(llm, max_messages=20, keep_recent=4)
        history = build_history(5)  # 11 messages
        assert compactor.compact_if_needed(history) is False
        assert len(history) == 11

    def test_compacts_old_messages_into_a_summary(self) -> None:
        llm = FakeLLMClient([AssistantTurn(text="THE SUMMARY")])
        compactor = ContextCompactor(llm, max_messages=10, keep_recent=4)
        history = build_history(8)  # 17 messages

        assert compactor.compact_if_needed(history) is True

        messages = history.messages()
        assert messages[0].content == "system prompt"  # system prompt preserved
        assert messages[1].role is Role.USER
        assert SUMMARY_PREFIX in messages[1].content
        assert "THE SUMMARY" in messages[1].content
        assert messages[-1].content == "answer 7"  # recent tail preserved
        assert len(messages) < 17
        # the summarization request saw the old span plus the instruction
        request_messages = llm.requests[0][0]
        assert request_messages[-1].role is Role.USER
        assert "Summarize" in request_messages[-1].content

    def test_split_never_separates_a_tool_call_from_its_result(self) -> None:
        history = ConversationHistory("system prompt")
        for index in range(6):
            history.add_user(f"question {index}")
            call = ToolCall(id=str(index), name="echo", arguments={})
            history.add_assistant(AssistantTurn(text=None, tool_calls=(call,)))
            history.add_tool_result(ToolResult(tool_call_id=str(index), content="ok"))
            history.add_assistant_text(f"answer {index}")
        llm = FakeLLMClient([AssistantTurn(text="summary")])
        compactor = ContextCompactor(llm, max_messages=10, keep_recent=4)

        assert compactor.compact_if_needed(history) is True

        messages = history.messages()
        # the message right after the summary must start a fresh exchange
        assert messages[2].role is Role.USER
        for index, message in enumerate(messages):
            if message.tool_calls:
                assert messages[index + 1].role is Role.TOOL

    def test_invalid_configuration_raises(self) -> None:
        with pytest.raises(ValueError):
            ContextCompactor(FakeLLMClient([]), max_messages=4, keep_recent=4)
