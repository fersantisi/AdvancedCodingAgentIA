"""Embeddings provider abstraction.

``OpenAIEmbeddings`` calls the REST endpoint directly with ``httpx`` (same
pattern as the Tavily provider), so ``llm/openai_client.py`` remains the only
module importing the ``openai`` SDK. ``NullEmbeddings`` makes RAG fail
gracefully when no API key is configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx

_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
_TIMEOUT_SECONDS = 30.0


class EmbeddingsError(Exception):
    """Raised when texts could not be embedded."""


class EmbeddingsProvider(ABC):
    """Contract every embeddings backend must fulfil."""

    model: str

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order.

        Raises:
            EmbeddingsError: on any failure, with a message the caller can act on.
        """


class OpenAIEmbeddings(EmbeddingsProvider):
    """OpenAI embeddings via plain REST calls."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = httpx.post(
                _OPENAI_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model, "input": list(texts)},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingsError(
                f"Embeddings request failed with HTTP {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingsError(f"Could not reach the embeddings API: {exc}") from exc

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingsError("Embeddings API returned an unexpected payload")
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in ordered]


class NullEmbeddings(EmbeddingsProvider):
    """Used when embeddings are not configured; always fails gracefully."""

    model = "none"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingsError(
            "Embeddings are not configured (OPENAI_API_KEY is missing), so RAG is unavailable."
        )
