"""Search-provider abstraction: Tavily today, any provider tomorrow."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SearchError(Exception):
    """Raised when a web search cannot be performed."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    """Contract for web-search backends."""

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return up to ``max_results`` results for ``query``.

        Raises:
            SearchError: if the search fails or the provider is unavailable.
        """


class NullSearchProvider(SearchProvider):
    """Used when no search provider is configured; fails with a clear message."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        raise SearchError(
            "Web search is not configured. Set TAVILY_API_KEY in your environment "
            "(or .env file) to enable it."
        )
