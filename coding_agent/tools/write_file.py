"""write_file tool: overwrite (or create) a file with the given content."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import Tool, ToolError, require_string


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write text content to a file, replacing its current content. "
        "Creates the file (and parent directories) if missing."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path of the file to write."},
            "content": {"type": "string", "description": "Full new content of the file."},
        },
        "required": ["path", "content"],
    }
    read_only = False

    def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(require_string(arguments, "path"))
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ToolError("Missing or invalid required argument 'content' (expected a string)")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except PermissionError:
            raise ToolError(f"Permission denied writing: {path}") from None
        except IsADirectoryError:
            raise ToolError(f"'{path}' is a directory; cannot overwrite it with a file") from None
        except OSError as exc:
            raise ToolError(f"Could not write '{path}': {exc}") from exc
        return f"Wrote {len(content)} characters to {path}"
