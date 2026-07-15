"""Ingestion: build the RAG index from a directory of documentation.

Run as a module:

    python -m coding_agent.rag.ingest <docs_dir> [--store rag_index.json]

Reads every matching file, chunks it, embeds the chunks in batches and saves
the vector store. Requires OPENAI_API_KEY (from .env or the environment).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from coding_agent.config.settings import Settings, SettingsError
from coding_agent.rag.chunking import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP, Chunk, chunk_text
from coding_agent.rag.embeddings import EmbeddingsError, EmbeddingsProvider, OpenAIEmbeddings
from coding_agent.rag.store import VectorStore

DEFAULT_PATTERNS = ("*.md", "*.mdx", "*.txt", "*.rst")
_BATCH_SIZE = 64


def ingest_directory(
    docs_dir: Path,
    store_path: Path,
    embeddings: EmbeddingsProvider,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> tuple[int, int]:
    """Chunk and embed every matching file; returns (files, chunks) ingested.

    Raises:
        EmbeddingsError: if the embeddings backend fails.
        ValueError: if the docs directory does not exist or has no matching files.
    """
    if not docs_dir.is_dir():
        raise ValueError(f"Documentation directory not found: {docs_dir}")

    files = sorted({file for pattern in patterns for file in docs_dir.rglob(pattern)})
    if not files:
        raise ValueError(
            f"No documentation files matching {', '.join(patterns)} under {docs_dir}"
        )

    chunks: list[Chunk] = []
    for file in files:
        text = file.read_text(encoding="utf-8", errors="replace")
        source = file.relative_to(docs_dir).as_posix()
        chunks.extend(chunk_text(text, source, max_chars=max_chars, overlap=overlap))

    store = VectorStore(store_path, model=embeddings.model)
    for start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[start : start + _BATCH_SIZE]
        store.add(batch, embeddings.embed([chunk.text for chunk in batch]))
    store.save()
    return len(files), len(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the RAG index from documentation files")
    parser.add_argument("docs_dir", type=Path, help="Directory containing the documentation")
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Output index file (default: RAG_STORE_PATH from settings, rag_index.json)",
    )
    parser.add_argument(
        "--patterns",
        nargs="+",
        default=list(DEFAULT_PATTERNS),
        help=f"Glob patterns of files to ingest (default: {' '.join(DEFAULT_PATTERNS)})",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
        settings.validate()
    except SettingsError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    embeddings = OpenAIEmbeddings(settings.openai_api_key, model=settings.embeddings_model)
    store_path = args.store or settings.rag_store_path
    try:
        files, chunks = ingest_directory(args.docs_dir, store_path, embeddings, args.patterns)
    except (ValueError, EmbeddingsError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1

    print(f"Ingested {files} file(s) into {chunks} chunk(s) -> {store_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
