"""rag_search tool: retrieve relevant fragments from the RAG documentation index.

Returns the retrieved fragments with their sources and similarity scores, so
the agent can show which documents it used. Records every consulted fragment
in the shared task state (origin=rag) and reports the retrieval to the tracer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.models import SourceOrigin, SourceRecord, TaskState
from coding_agent.observability.base import Tracer
from coding_agent.rag.embeddings import EmbeddingsError, EmbeddingsProvider
from coding_agent.rag.store import VectorStore, VectorStoreError
from coding_agent.tools.base import Tool, ToolError, require_string

_MAX_TOP_K = 10
_DEFAULT_TOP_K = 4


class RagSearchTool(Tool):
    name = "rag_search"
    description = (
        "Search the project's RAG documentation index and return the most relevant "
        "fragments with their sources. Use this BEFORE web_search for questions about "
        "the ecosystem's documentation."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for in the documentation."},
            "top_k": {
                "type": "integer",
                "description": f"Number of fragments to return (1-{_MAX_TOP_K}, default {_DEFAULT_TOP_K}).",
            },
        },
        "required": ["query"],
    }
    read_only = True

    def __init__(
        self,
        store_path: Path,
        embeddings: EmbeddingsProvider,
        state: TaskState | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._store_path = store_path
        self._embeddings = embeddings
        self._state = state
        self._tracer = tracer
        self._store: VectorStore | None = None

    def execute(self, arguments: dict[str, Any]) -> str:
        query = require_string(arguments, "query")
        top_k = arguments.get("top_k", _DEFAULT_TOP_K)
        if not isinstance(top_k, int) or not 1 <= top_k <= _MAX_TOP_K:
            top_k = _DEFAULT_TOP_K

        store = self._load_store()
        try:
            query_embedding = self._embeddings.embed([query])[0]
        except EmbeddingsError as exc:
            raise ToolError(str(exc)) from exc

        hits = store.search(query_embedding, top_k=top_k)
        if not hits:
            return f"The RAG index returned no fragments for: {query}"

        if self._state is not None:
            for hit in hits:
                self._state.add_source(
                    SourceRecord(origin=SourceOrigin.RAG, reference=hit.source)
                )
        if self._tracer is not None:
            self._tracer.record_retrieval(query=query, sources=[hit.source for hit in hits])

        blocks = [
            f"{index}. [source: {hit.source} | relevance: {hit.score:.2f}]\n{hit.text}"
            for index, hit in enumerate(hits, start=1)
        ]
        return "\n\n".join(blocks)

    def _load_store(self) -> VectorStore:
        if self._store is None:
            try:
                self._store = VectorStore.load(self._store_path)
            except VectorStoreError as exc:
                raise ToolError(str(exc)) from exc
        if len(self._store) == 0:
            raise ToolError(
                f"The RAG index at '{self._store_path}' is empty — rebuild it with: "
                "python -m coding_agent.rag.ingest <docs_dir>"
            )
        return self._store
