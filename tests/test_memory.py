"""Tests for the persistent project memory and the remember tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent.agent.memory import MEMORY_CATEGORIES, ProjectMemory
from coding_agent.tools import ToolError
from coding_agent.tools.remember import RememberTool


class TestProjectMemory:
    def test_starts_empty_without_a_file(self, tmp_path: Path) -> None:
        memory = ProjectMemory(tmp_path / ".agent" / "memory.json")
        assert memory.is_empty()
        assert memory.render() == "(no project memory recorded yet)"

    def test_remember_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / ".agent" / "memory.json"
        ProjectMemory(path).remember("architecture", "Laravel API with Blade views")

        reloaded = ProjectMemory(path)
        assert not reloaded.is_empty()
        assert "Laravel API with Blade views" in reloaded.render()
        assert "architecture:" in reloaded.render()

    def test_remember_deduplicates_notes(self, tmp_path: Path) -> None:
        memory = ProjectMemory(tmp_path / "memory.json")
        memory.remember("commands", "run tests with: php artisan test")
        memory.remember("commands", "run tests with: php artisan test")
        assert memory.render().count("php artisan test") == 1

    def test_unknown_category_raises(self, tmp_path: Path) -> None:
        memory = ProjectMemory(tmp_path / "memory.json")
        with pytest.raises(ValueError, match="Unknown memory category"):
            memory.remember("gossip", "something")

    def test_corrupt_file_starts_fresh(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text("{not json", encoding="utf-8")
        memory = ProjectMemory(path)
        assert memory.is_empty()
        memory.remember("decisions", "use JSON for config")  # and it can still save
        assert json.loads(path.read_text(encoding="utf-8"))["notes"]["decisions"]

    def test_session_summaries_keep_only_the_most_recent(self, tmp_path: Path) -> None:
        memory = ProjectMemory(tmp_path / "memory.json")
        for index in range(12):
            memory.add_session_summary(f"session {index:02d}")
        rendered = memory.render()
        assert "session 11" in rendered
        assert "session 00" not in rendered
        assert "session 01" not in rendered


class TestRememberTool:
    def test_execute_saves_the_note(self, tmp_path: Path) -> None:
        memory = ProjectMemory(tmp_path / "memory.json")
        tool = RememberTool(memory, MEMORY_CATEGORIES)
        output = tool.execute({"category": "conventions", "note": "controllers are thin"})
        assert "Remembered under 'conventions'" in output
        assert "controllers are thin" in memory.render()

    def test_invalid_category_becomes_tool_error(self, tmp_path: Path) -> None:
        tool = RememberTool(ProjectMemory(tmp_path / "memory.json"), MEMORY_CATEGORIES)
        with pytest.raises(ToolError, match="Unknown memory category"):
            tool.execute({"category": "nope", "note": "x"})

    def test_schema_lists_the_categories(self, tmp_path: Path) -> None:
        tool = RememberTool(ProjectMemory(tmp_path / "memory.json"), MEMORY_CATEGORIES)
        assert tool.parameters["properties"]["category"]["enum"] == list(MEMORY_CATEGORIES)
