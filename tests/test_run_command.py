"""Unit tests for the run_command tool."""

from __future__ import annotations

import sys

import pytest

from coding_agent.tools.base import ToolError
from coding_agent.tools.run_command import RunCommandTool


def _python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


class TestRunCommand:
    def test_captures_stdout_and_exit_code_zero(self):
        output = RunCommandTool().execute({"command": _python("print('hola')")})
        assert "exit_code: 0" in output
        assert "hola" in output

    def test_captures_stderr_and_nonzero_exit_code(self):
        code = "import sys; sys.stderr.write('boom'); sys.exit(3)"
        output = RunCommandTool().execute({"command": _python(code)})
        assert "exit_code: 3" in output
        assert "boom" in output

    def test_timeout_raises_tool_error(self):
        tool = RunCommandTool(timeout_seconds=1)
        with pytest.raises(ToolError, match="timed out"):
            tool.execute({"command": _python("import time; time.sleep(5)")})

    def test_missing_command_raises(self):
        with pytest.raises(ToolError, match="command"):
            RunCommandTool().execute({})

    def test_respects_working_dir(self, tmp_path):
        (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
        code = "import os; print(sorted(os.listdir()))"
        output = RunCommandTool().execute(
            {"command": _python(code), "working_dir": str(tmp_path)}
        )
        assert "marker.txt" in output
