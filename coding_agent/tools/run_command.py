"""run_command tool: execute a shell command, capturing stdout/stderr/exit code."""

from __future__ import annotations

import subprocess
from typing import Any

from coding_agent.tools.base import Tool, ToolError, require_string
from coding_agent.utils import truncate


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Execute a terminal command through the system shell and return its "
        "exit code, stdout and stderr. A non-zero exit code is reported in the "
        "output, not treated as a tool failure."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "working_dir": {
                "type": "string",
                "description": "Directory to run the command in. Defaults to the current directory.",
            },
        },
        "required": ["command"],
    }
    read_only = False

    def __init__(self, timeout_seconds: float = 60.0, max_output_chars: int = 10_000) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars

    def execute(self, arguments: dict[str, Any]) -> str:
        command = require_string(arguments, "command")
        working_dir = arguments.get("working_dir") or None
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self._timeout_seconds,
                cwd=working_dir,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(
                f"Command timed out after {self._timeout_seconds:.0f}s: {command}"
            ) from None
        except (OSError, NotADirectoryError) as exc:
            raise ToolError(f"Could not start command: {exc}") from exc

        return "\n".join(
            [
                f"exit_code: {completed.returncode}",
                "stdout:",
                truncate(completed.stdout or "(empty)", self._max_output_chars),
                "stderr:",
                truncate(completed.stderr or "(empty)", self._max_output_chars),
            ]
        )
