"""count_lines plugin tool: report how many lines a text file has.

Sample plugin demonstrating auto-discovery: a concrete, read-only ``Tool`` with
a no-argument constructor. Dropping this module in ``tools/plugins/`` is enough
for it to be registered automatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolError, require_string


class CountLinesTool(Tool):
    name = "count_lines"
    description = "Count the number of lines in a text file at the given path."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to count lines in."},
        },
        "required": ["path"],
    }
    read_only = True

    def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(require_string(arguments, "path"))
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise ToolError(f"File not found: {path}") from None
        except IsADirectoryError:
            raise ToolError(f"'{path}' is a directory, not a file") from None
        except PermissionError:
            raise ToolError(f"Permission denied reading: {path}") from None
        except OSError as exc:
            raise ToolError(f"Could not read '{path}': {exc}") from exc
        return f"{len(content.splitlines())}"
