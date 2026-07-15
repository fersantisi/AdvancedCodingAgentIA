"""Tests for the shared TaskState and its harness integration."""

from __future__ import annotations

import json
from pathlib import Path

from coding_agent.models import (
    AssistantTurn,
    SourceOrigin,
    SourceRecord,
    SubAgentReport,
    TaskState,
    ToolCall,
)
from coding_agent.tools.write_file import WriteFileTool
from tests.conftest import FakeIO, make_harness


class TestTaskState:
    def test_first_request_is_original_later_ones_are_progress(self) -> None:
        state = TaskState()
        state.record_request("fix the bug")
        state.record_request("also add a test")
        assert state.request == "fix the bug"
        assert state.progress == ["New user request: also add a test"]

    def test_files_modified_deduplicates(self) -> None:
        state = TaskState()
        state.add_file_modified("a.py")
        state.add_file_modified("a.py")
        assert state.files_modified == ["a.py"]

    def test_render_shows_every_section(self) -> None:
        state = TaskState()
        state.record_request("analyze the repo")
        state.add_progress("explored the structure")
        state.add_report(SubAgentReport(agent="explorer", task="map repo", summary="it is Laravel"))
        state.add_source(SourceRecord(origin=SourceOrigin.RAG, reference="routing.md#chunk0"))
        state.add_file_modified("app/Models/User.php")
        state.add_observation("tests are failing")

        rendered = state.render()
        assert "analyze the repo" in rendered
        assert "explored the structure" in rendered
        assert "explorer (ok): it is Laravel" in rendered
        assert "[rag] routing.md#chunk0" in rendered
        assert "app/Models/User.php" in rendered
        assert "tests are failing" in rendered

    def test_to_json_round_trips(self) -> None:
        state = TaskState()
        state.record_request("do something")
        state.add_source(SourceRecord(origin=SourceOrigin.WEB, reference="https://laravel.com"))
        data = json.loads(state.to_json())
        assert data["request"] == "do something"
        assert data["sources"] == [
            {"origin": "web", "reference": "https://laravel.com", "detail": ""}
        ]


class TestHarnessIntegration:
    def test_successful_write_records_file_modified(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        call = ToolCall(id="1", name="write_file", arguments={"path": str(target), "content": "hi"})
        turns = [AssistantTurn(text=None, tool_calls=(call,)), AssistantTurn(text="done")]
        state = TaskState()
        harness, _, _ = make_harness(turns, FakeIO(), tools=[WriteFileTool()], state=state)

        harness.run_turn("write the file")
        assert state.files_modified == [str(target)]

    def test_failed_tool_records_observation(self) -> None:
        call = ToolCall(id="1", name="missing_tool", arguments={})
        turns = [AssistantTurn(text=None, tool_calls=(call,)), AssistantTurn(text="done")]
        state = TaskState()
        harness, _, _ = make_harness(turns, FakeIO(), state=state)

        harness.run_turn("try something")
        assert state.observations
        assert "missing_tool failed" in state.observations[0]
