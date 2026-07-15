"""Vector store: JSON-persisted embeddings with pure-Python cosine search.

Deliberately dependency-free: for a documentation-sized corpus (hundreds to a
few thousand chunks) a linear cosine scan is instant, and the ``VectorStore``
seam allows swapping in a real vector database later without touching callers.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from coding_agent.rag.chunking import Chunk


class VectorStoreError(Exception):
    """Raised when the index file is missing, corrupt or inconsistent."""


@dataclass(frozen=True)
class ScoredChunk:
    """One search hit: the fragment, where it came from and its similarity."""

    text: str
    source: str
    score: float


class VectorStore:
    """In-memory list of (chunk, embedding) pairs persisted as one JSON file."""

    def __init__(self, path: Path, model: str = "") -> None:
        self._path = path
        self._model = model
        self._entries: list[dict] = []

    @classmethod
    def load(cls, path: Path) -> VectorStore:
        """Load an existing index.

        Raises:
            VectorStoreError: if the file is missing or invalid.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise VectorStoreError(
                f"RAG index not found at '{path}'. Build it first with: "
                "python -m coding_agent.rag.ingest <docs_dir>"
            ) from None
        except (json.JSONDecodeError, OSError) as exc:
            raise VectorStoreError(f"Could not read RAG index '{path}': {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise VectorStoreError(f"RAG index '{path}' has an unexpected format")

        store = cls(path, model=str(data.get("model", "")))
        store._entries = data["entries"]
        return store

    @property
    def model(self) -> str:
        """Name of the embeddings model the index was built with."""
        return self._model

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise VectorStoreError(
                f"Got {len(chunks)} chunks but {len(embeddings)} embeddings"
            )
        for chunk, embedding in zip(chunks, embeddings):
            self._entries.append(
                {
                    "text": chunk.text,
                    "source": chunk.source,
                    "index": chunk.index,
                    "embedding": list(embedding),
                }
            )

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"model": self._model, "entries": self._entries}
        self._path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def search(self, query_embedding: Sequence[float], top_k: int = 4) -> list[ScoredChunk]:
        """The ``top_k`` most similar chunks by cosine similarity."""
        scored = [
            ScoredChunk(
                text=entry["text"],
                source=f"{entry['source']}#chunk{entry['index']}",
                score=_cosine(query_embedding, entry["embedding"]),
            )
            for entry in self._entries
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
