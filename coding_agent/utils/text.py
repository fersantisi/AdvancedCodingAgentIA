"""Text helpers shared by tools and the CLI."""

from __future__ import annotations


def truncate(text: str, max_chars: int) -> str:
    """Cap ``text`` at ``max_chars``, appending a note when content was cut."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n... [truncated, {omitted} characters omitted]"
