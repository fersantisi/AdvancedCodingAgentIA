"""RAG: chunking, embeddings and vector storage over the chosen ecosystem's docs."""

from coding_agent.rag.chunking import Chunk, chunk_text
from coding_agent.rag.embeddings import (
    EmbeddingsError,
    EmbeddingsProvider,
    NullEmbeddings,
    OpenAIEmbeddings,
)
from coding_agent.rag.store import ScoredChunk, VectorStore

__all__ = [
    "Chunk",
    "EmbeddingsError",
    "EmbeddingsProvider",
    "NullEmbeddings",
    "OpenAIEmbeddings",
    "ScoredChunk",
    "VectorStore",
    "chunk_text",
]
