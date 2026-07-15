"""Tests for the web_search tool and its provider abstraction."""

from __future__ import annotations

import pytest

from coding_agent.tools.base import ToolError
from coding_agent.tools.web_search import NullSearchProvider, SearchResult, WebSearchTool
from tests.conftest import FakeSearchProvider

RESULTS = [
    SearchResult(title="Result A", url="https://a.example", snippet="about A"),
    SearchResult(title="Result B", url="https://b.example", snippet="about B"),
]


class TestWebSearchTool:
    def test_formats_numbered_results(self):
        tool = WebSearchTool(FakeSearchProvider(RESULTS))
        output = tool.execute({"query": "anything"})
        assert "1. Result A" in output
        assert "https://b.example" in output

    def test_respects_max_results(self):
        tool = WebSearchTool(FakeSearchProvider(RESULTS))
        output = tool.execute({"query": "anything", "max_results": 1})
        assert "Result A" in output
        assert "Result B" not in output

    def test_no_results_message(self):
        tool = WebSearchTool(FakeSearchProvider([]))
        assert "No results" in tool.execute({"query": "obscure"})

    def test_missing_query_raises(self):
        with pytest.raises(ToolError, match="query"):
            WebSearchTool(FakeSearchProvider(RESULTS)).execute({})

    def test_null_provider_reports_not_configured(self):
        with pytest.raises(ToolError, match="not configured"):
            WebSearchTool(NullSearchProvider()).execute({"query": "x"})
