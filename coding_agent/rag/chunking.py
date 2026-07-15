"""Chunking: split documents into overlapping, paragraph-aware fragments.

Strategy: split on blank lines, merge consecutive paragraphs up to
``max_chars``, and hard-split oversized paragraphs with ``overlap`` characters
of carry-over so no statement is lost at a boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1_500
DEFAULT_OVERLAP = 200


@dataclass(frozen=True)
class Chunk:
    """One indexed fragment of a source document."""

    text: str
    source: str
    index: int


def chunk_text(
    text: str,
    source: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split ``text`` into chunks of at most ``max_chars`` characters."""
    if not 0 <= overlap < max_chars:
        raise ValueError("expected 0 <= overlap < max_chars")

    pieces: list[str] = []
    for paragraph in (part.strip() for part in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            pieces.extend(_hard_split(paragraph, max_chars, overlap))

    merged: list[str] = []
    buffer = ""
    for piece in pieces:
        candidate = f"{buffer}\n\n{piece}" if buffer else piece
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            merged.append(buffer)
            buffer = piece
    if buffer:
        merged.append(buffer)

    return [Chunk(text=chunk, source=source, index=index) for index, chunk in enumerate(merged)]


def _hard_split(paragraph: str, max_chars: int, overlap: int) -> list[str]:
    step = max_chars - overlap
    parts = []
    for start in range(0, len(paragraph), step):
        parts.append(paragraph[start : start + max_chars])
        if start + max_chars >= len(paragraph):
            break
    return parts
