"""list_files tool: list the entries of a directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolError


class ListFilesTool(Tool):
    name = "list_files"
    description = (
        "List the files and subdirectories in a directory (non-recursive). "
        "Directories are marked with a trailing '/'."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list. Defaults to the current working directory.",
            },
        },
        "required": [],
    }
    read_only = True

    def execute(self, arguments: dict[str, Any]) -> str:
        raw = arguments.get("path") or "."
        if not isinstance(raw, str):
            raise ToolError("Invalid argument 'path' (expected a string)")
        directory = Path(raw)
        if not directory.exists():
            raise ToolError(f"Directory not found: {directory}")
        if not directory.is_dir():
            raise ToolError(f"'{directory}' is not a directory (use read_file)")
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            raise ToolError(f"Permission denied listing: {directory}") from None
        if not entries:
            return f"(directory '{directory}' is empty)"
        lines = [f"{entry.name}/" if entry.is_dir() else entry.name for entry in entries]
        return "\n".join(lines)
