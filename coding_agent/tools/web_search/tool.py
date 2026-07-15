"""web_search tool: query the configured search provider."""

from __future__ import annotations

from typing import Any

from coding_agent.tools.base import Tool, ToolError, require_string
from coding_agent.tools.web_search.provider import SearchError, SearchProvider

_MAX_RESULTS_LIMIT = 10


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return the top results (title, URL and snippet)."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (1-10, default 5).",
            },
        },
        "required": ["query"],
    }
    read_only = True

    def __init__(self, provider: SearchProvider) -> None:
        self._provider = provider

    def execute(self, arguments: dict[str, Any]) -> str:
        query = require_string(arguments, "query")
        max_results = arguments.get("max_results", 5)
        if not isinstance(max_results, int) or not 1 <= max_results <= _MAX_RESULTS_LIMIT:
            max_results = 5

        try:
            results = self._provider.search(query, max_results)
        except SearchError as exc:
            raise ToolError(str(exc)) from exc

        if not results:
            return f"No results found for: {query}"
        blocks = [
            f"{index}. {result.title}\n   {result.url}\n   {result.snippet}"
            for index, result in enumerate(results, start=1)
        ]
        return "\n".join(blocks)
