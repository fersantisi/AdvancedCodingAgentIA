"""Unit tests for read_file, write_file and list_files."""

from __future__ import annotations

import pytest

from coding_agent.tools.base import ToolError
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.write_file import WriteFileTool


class TestReadFile:
    def test_reads_content(self, tmp_path):
        target = tmp_path / "hello.txt"
        target.write_text("hello world", encoding="utf-8")
        assert ReadFileTool().execute({"path": str(target)}) == "hello world"

    def test_missing_file_raises_tool_error(self, tmp_path):
        with pytest.raises(ToolError, match="not found"):
            ReadFileTool().execute({"path": str(tmp_path / "nope.txt")})

    def test_directory_raises_tool_error(self, tmp_path):
        with pytest.raises(ToolError, match="directory"):
            ReadFileTool().execute({"path": str(tmp_path)})

    def test_missing_argument(self):
        with pytest.raises(ToolError, match="path"):
            ReadFileTool().execute({})

    def test_truncates_large_files(self, tmp_path):
        target = tmp_path / "big.txt"
        target.write_text("x" * 100, encoding="utf-8")
        output = ReadFileTool(max_output_chars=10).execute({"path": str(target)})
        assert output.startswith("x" * 10)
        assert "truncated" in output


class TestWriteFile:
    def test_writes_and_overwrites(self, tmp_path):
        target = tmp_path / "out.txt"
        tool = WriteFileTool()
        tool.execute({"path": str(target), "content": "first"})
        result = tool.execute({"path": str(target), "content": "second"})
        assert target.read_text(encoding="utf-8") == "second"
        assert "6 characters" in result

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "a" / "b" / "out.txt"
        WriteFileTool().execute({"path": str(target), "content": "deep"})
        assert target.read_text(encoding="utf-8") == "deep"

    def test_missing_content_raises(self, tmp_path):
        with pytest.raises(ToolError, match="content"):
            WriteFileTool().execute({"path": str(tmp_path / "x.txt")})


class TestListFiles:
    def test_lists_directories_first_with_marker(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "file.txt").write_text("x", encoding="utf-8")
        output = ListFilesTool().execute({"path": str(tmp_path)})
        assert output.splitlines() == ["sub/", "file.txt"]

    def test_empty_directory(self, tmp_path):
        assert "empty" in ListFilesTool().execute({"path": str(tmp_path)})

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(ToolError, match="not found"):
            ListFilesTool().execute({"path": str(tmp_path / "ghost")})

    def test_file_path_raises(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("x", encoding="utf-8")
        with pytest.raises(ToolError, match="not a directory"):
            ListFilesTool().execute({"path": str(target)})
