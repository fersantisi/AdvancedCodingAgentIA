"""Tests for the RAG package: chunking, vector store, ingestion and the tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.models import SourceOrigin, TaskState
from coding_agent.rag.chunking import chunk_text
from coding_agent.rag.embeddings import NullEmbeddings
from coding_agent.rag.ingest import ingest_directory
from coding_agent.rag.store import VectorStore, VectorStoreError
from coding_agent.tools import ToolError
from coding_agent.tools.rag_search import RagSearchTool
from tests.conftest import FakeEmbeddings, FakeTracer


class TestChunking:
    def test_short_text_is_one_chunk(self) -> None:
        chunks = chunk_text("hello world", "doc.md")
        assert len(chunks) == 1
        assert chunks[0].source == "doc.md"
        assert chunks[0].index == 0

    def test_paragraphs_merge_up_to_the_limit(self) -> None:
        text = "\n\n".join(["alpha " * 10, "beta " * 10, "gamma " * 10])
        chunks = chunk_text(text, "doc.md", max_chars=130, overlap=20)
        assert len(chunks) > 1
        assert all(len(chunk.text) <= 130 for chunk in chunks)
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))

    def test_oversized_paragraph_is_split_with_overlap(self) -> None:
        text = "".join(f"{i:03d}" for i in range(167))[:500]  # positionally unique
        chunks = chunk_text(text, "doc.md", max_chars=200, overlap=50)
        assert len(chunks) == 3  # starts at 0, 150, 300 (step = max_chars - overlap)
        assert chunks[0].text[-50:] == chunks[1].text[:50]
        assert chunks[1].text[-50:] == chunks[2].text[:50]

    def test_invalid_overlap_raises(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("text", "doc.md", max_chars=100, overlap=100)


class TestVectorStore:
    def test_save_load_and_search_ranks_by_similarity(self, tmp_path: Path) -> None:
        embeddings = FakeEmbeddings()
        docs = [
            "laravel routing controllers middleware",
            "python decorators generators iterators",
        ]
        chunks = [chunk for doc in docs for chunk in chunk_text(doc, f"doc{docs.index(doc)}.md")]
        store = VectorStore(tmp_path / "index.json", model=embeddings.model)
        store.add(chunks, embeddings.embed([chunk.text for chunk in chunks]))
        store.save()

        loaded = VectorStore.load(tmp_path / "index.json")
        assert len(loaded) == 2
        assert loaded.model == embeddings.model
        hits = loaded.search(embeddings.embed(["laravel routing"])[0], top_k=2)
        assert hits[0].source.startswith("doc0.md")
        assert hits[0].score > hits[1].score

    def test_load_missing_index_raises_with_ingest_hint(self, tmp_path: Path) -> None:
        with pytest.raises(VectorStoreError, match="coding_agent.rag.ingest"):
            VectorStore.load(tmp_path / "missing.json")

    def test_mismatched_lengths_raise(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "index.json")
        with pytest.raises(VectorStoreError):
            store.add(chunk_text("text", "doc.md"), [])


class TestIngestion:
    def test_ingest_directory_builds_the_store(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        (docs / "nested").mkdir(parents=True)
        (docs / "routing.md").write_text("Laravel routing maps URLs to controllers.", encoding="utf-8")
        (docs / "nested" / "views.txt").write_text("Blade is the templating engine.", encoding="utf-8")
        store_path = tmp_path / "index.json"

        files, chunks = ingest_directory(docs, store_path, FakeEmbeddings())

        assert files == 2
        assert chunks >= 2
        store = VectorStore.load(store_path)
        assert len(store) == chunks
        hits = store.search(FakeEmbeddings().embed(["laravel routing"])[0], top_k=1)
        assert hits[0].source.startswith("routing.md")

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            ingest_directory(tmp_path / "nope", tmp_path / "index.json", FakeEmbeddings())

    def test_directory_without_docs_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "docs"
        empty.mkdir()
        with pytest.raises(ValueError, match="No documentation files"):
            ingest_directory(empty, tmp_path / "index.json", FakeEmbeddings())


def build_index(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "routing.md").write_text(
        "Laravel routing maps URLs to controllers.\n\nRoutes live in routes/web.php.",
        encoding="utf-8",
    )
    store_path = tmp_path / "index.json"
    ingest_directory(docs, store_path, FakeEmbeddings())
    return store_path


class TestRagSearchTool:
    def test_returns_labeled_fragments_and_records_sources(self, tmp_path: Path) -> None:
        store_path = build_index(tmp_path)
        state = TaskState()
        tracer = FakeTracer()
        tool = RagSearchTool(store_path, FakeEmbeddings(), state=state, tracer=tracer)

        output = tool.execute({"query": "laravel routing", "top_k": 2})

        assert "[source: routing.md#chunk0" in output
        assert "relevance:" in output
        assert state.sources and all(s.origin is SourceOrigin.RAG for s in state.sources)
        assert tracer.retrievals[0][0] == "laravel routing"
        assert tracer.retrievals[0][1]  # sources reported

    def test_missing_index_is_a_tool_error_with_instructions(self, tmp_path: Path) -> None:
        tool = RagSearchTool(tmp_path / "missing.json", FakeEmbeddings())
        with pytest.raises(ToolError, match="coding_agent.rag.ingest"):
            tool.execute({"query": "anything"})

    def test_unconfigured_embeddings_fail_gracefully(self, tmp_path: Path) -> None:
        store_path = build_index(tmp_path)
        tool = RagSearchTool(store_path, NullEmbeddings())
        with pytest.raises(ToolError, match="not configured"):
            tool.execute({"query": "anything"})
