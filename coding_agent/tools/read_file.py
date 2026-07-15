"""read_file tool: return the contents of a file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolError, require_string
from coding_agent.utils import truncate


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read and return the full text content of a file at the given path."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."},
        },
        "required": ["path"],
    }
    read_only = True

    def __init__(self, max_output_chars: int = 50_000) -> None:
        self._max_output_chars = max_output_chars

    def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(require_string(arguments, "path"))
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise ToolError(f"File not found: {path}") from None
        except IsADirectoryError:
            raise ToolError(f"'{path}' is a directory, not a file (use list_files)") from None
        except PermissionError:
            raise ToolError(f"Permission denied reading: {path}") from None
        except OSError as exc:
            raise ToolError(f"Could not read '{path}': {exc}") from exc
        if not content:
            return f"(file '{path}' is empty)"
        return truncate(content, self._max_output_chars)
