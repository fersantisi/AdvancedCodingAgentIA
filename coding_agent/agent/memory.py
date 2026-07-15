"""Persistent project memory: knowledge that survives across sessions.

Stored as a JSON file per project (default ``.agent/memory.json``): categorized
notes (architecture, key files, dependencies, useful commands, conventions,
decisions, investigated bugs) plus summaries of previous sessions. Loaded at
startup into the system prompt; extended during the session through the
``remember`` tool and a session summary written on exit.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_CATEGORIES: tuple[str, ...] = (
    "architecture",
    "key_files",
    "dependencies",
    "commands",
    "conventions",
    "decisions",
    "bugs",
)

_MAX_SESSION_SUMMARIES = 10


class ProjectMemory:
    """Categorized project notes persisted to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._notes: dict[str, list[str]] = {category: [] for category in MEMORY_CATEGORIES}
        self._session_summaries: list[str] = []
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def remember(self, category: str, note: str) -> None:
        """Add one note under a category and persist immediately.

        Raises:
            ValueError: if the category is unknown.
        """
        if category not in MEMORY_CATEGORIES:
            known = ", ".join(MEMORY_CATEGORIES)
            raise ValueError(f"Unknown memory category '{category}'. Valid categories: {known}")
        note = note.strip()
        if not note:
            raise ValueError("Cannot remember an empty note")
        if note not in self._notes[category]:
            self._notes[category].append(note)
            self._save()
            logger.info("Memory: remembered under '%s': %s", category, note)

    def add_session_summary(self, summary: str) -> None:
        """Append a session summary (keeps the most recent ones) and persist."""
        summary = summary.strip()
        if not summary:
            return
        self._session_summaries.append(summary)
        self._session_summaries = self._session_summaries[-_MAX_SESSION_SUMMARIES:]
        self._save()

    def is_empty(self) -> bool:
        return not self._session_summaries and not any(self._notes.values())

    def render(self) -> str:
        """Compact text view for prompts and the /memory command."""
        if self.is_empty():
            return "(no project memory recorded yet)"
        lines: list[str] = []
        for category in MEMORY_CATEGORIES:
            notes = self._notes[category]
            if notes:
                lines.append(f"{category}:")
                lines.extend(f"- {note}" for note in notes)
        if self._session_summaries:
            lines.append("previous sessions:")
            lines.extend(f"- {summary}" for summary in self._session_summaries)
        return "\n".join(lines)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            notes = data.get("notes", {})
            for category in MEMORY_CATEGORIES:
                entries = notes.get(category, [])
                if isinstance(entries, list):
                    self._notes[category] = [entry for entry in entries if isinstance(entry, str)]
            summaries = data.get("session_summaries", [])
            if isinstance(summaries, list):
                self._session_summaries = [entry for entry in summaries if isinstance(entry, str)]
            logger.info("Project memory loaded from %s", self._path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load project memory from %s: %s — starting fresh", self._path, exc)

    def _save(self) -> None:
        payload = {"notes": self._notes, "session_summaries": self._session_summaries}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not save project memory to %s: %s", self._path, exc)
