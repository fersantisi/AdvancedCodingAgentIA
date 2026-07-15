"""web_search tool with a pluggable search-provider abstraction."""

from coding_agent.tools.web_search.provider import (
    NullSearchProvider,
    SearchError,
    SearchProvider,
    SearchResult,
)
from coding_agent.tools.web_search.tavily import TavilyProvider
from coding_agent.tools.web_search.tool import WebSearchTool

__all__ = [
    "NullSearchProvider",
    "SearchError",
    "SearchProvider",
    "SearchResult",
    "TavilyProvider",
    "WebSearchTool",
]
