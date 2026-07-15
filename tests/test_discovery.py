"""Tests for tool plugin auto-discovery and the plugin allowlist policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent.config.policies import AgentPolicies
from coding_agent.tools import ToolRegistry
from coding_agent.tools.base import ToolError
from coding_agent.tools.discovery import discover_tools
from coding_agent.tools.plugins.count_lines import CountLinesTool


class TestDiscovery:
    def test_discovers_the_sample_plugin(self) -> None:
        names = [tool.name for tool in discover_tools()]
        assert "count_lines" in names

    def test_allowlist_includes_named_plugin(self) -> None:
        names = [tool.name for tool in discover_tools(allowlist=("count_lines",))]
        assert names == ["count_lines"]

    def test_empty_allowlist_loads_nothing(self) -> None:
        assert discover_tools(allowlist=()) == []

    def test_unknown_allowlist_entry_loads_nothing(self) -> None:
        assert discover_tools(allowlist=("does_not_exist",)) == []

    def test_missing_package_returns_empty(self) -> None:
        assert discover_tools(package="coding_agent.tools.no_such_package") == []

    def test_discovered_tool_registers_and_resolves(self) -> None:
        registry = ToolRegistry([])
        for tool in discover_tools(allowlist=("count_lines",)):
            registry.register(tool)
        assert registry.get("count_lines").name == "count_lines"


class TestCountLinesTool:
    def test_counts_lines(self, tmp_path: Path) -> None:
        file = tmp_path / "sample.txt"
        file.write_text("a\nb\nc\n", encoding="utf-8")
        assert CountLinesTool().execute({"path": str(file)}) == "3"

    def test_empty_file_is_zero(self, tmp_path: Path) -> None:
        file = tmp_path / "empty.txt"
        file.write_text("", encoding="utf-8")
        assert CountLinesTool().execute({"path": str(file)}) == "0"

    def test_missing_file_raises_toolerror(self, tmp_path: Path) -> None:
        with pytest.raises(ToolError, match="File not found"):
            CountLinesTool().execute({"path": str(tmp_path / "nope.txt")})


class TestPluginAllowlistPolicy:
    def _write_config(self, tmp_path: Path, payload: dict) -> Path:
        config = tmp_path / "agent.config.json"
        config.write_text(json.dumps(payload), encoding="utf-8")
        return config

    def test_absent_plugins_key_is_none(self, tmp_path: Path) -> None:
        config = self._write_config(tmp_path, {"workspace": "."})
        assert AgentPolicies.load(config).plugin_allowlist is None

    def test_enabled_list_is_parsed(self, tmp_path: Path) -> None:
        config = self._write_config(tmp_path, {"plugins": {"enabled": ["count_lines"]}})
        assert AgentPolicies.load(config).plugin_allowlist == ("count_lines",)

    def test_empty_enabled_list_is_empty_tuple(self, tmp_path: Path) -> None:
        config = self._write_config(tmp_path, {"plugins": {"enabled": []}})
        assert AgentPolicies.load(config).plugin_allowlist == ()

    def test_permissive_has_no_allowlist(self) -> None:
        assert AgentPolicies.permissive().plugin_allowlist is None
