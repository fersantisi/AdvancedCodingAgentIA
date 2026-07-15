"""Tavily search provider (https://tavily.com), via its public REST API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from coding_agent.tools.web_search.provider import SearchError, SearchProvider, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    def __init__(self, api_key: str, timeout_seconds: float = 20.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        payload = {"api_key": self._api_key, "query": query, "max_results": max_results}
        try:
            response = httpx.post(_API_URL, json=payload, timeout=self._timeout_seconds)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise SearchError(f"Tavily search timed out after {self._timeout_seconds:.0f}s") from None
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"Tavily returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchError(f"Network error calling Tavily: {exc}") from exc

        return _parse_results(response.json())


def _parse_results(data: Any) -> list[SearchResult]:
    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        raise SearchError("Unexpected response format from Tavily")
    results = []
    for item in raw_results:
        if isinstance(item, dict):
            results.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", "")),
                )
            )
    logger.debug("Tavily returned %d results", len(results))
    return results
