"""Shared task state: what the orchestrator and every subagent know about the task.

A single mutable ``TaskState`` instance is created at startup and injected into
the harness, the subagent runner and the tools that consult external sources.
It records the original request, progress notes, subagent reports, consulted
sources (labeled by origin), modified files and relevant observations — and it
can be rendered as compact text for prompts or serialized to JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum


class SourceOrigin(StrEnum):
    """Where a piece of information came from (the agent must label sources)."""

    REPO = "repo"
    MEMORY = "memory"
    RAG = "rag"
    WEB = "web"
    INFERENCE = "inference"


@dataclass(frozen=True)
class SourceRecord:
    """One consulted source: origin tag plus a human-readable reference."""

    origin: SourceOrigin
    reference: str
    detail: str = ""


@dataclass(frozen=True)
class SubAgentReport:
    """The outcome of one delegation to a subagent."""

    agent: str
    task: str
    summary: str
    success: bool = True


@dataclass
class TaskState:
    """Mutable session-wide task state shared by all agents."""

    request: str = ""
    progress: list[str] = field(default_factory=list)
    subagent_reports: list[SubAgentReport] = field(default_factory=list)
    sources: list[SourceRecord] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    def record_request(self, text: str) -> None:
        """Set the original request; later requests become progress notes."""
        if not self.request:
            self.request = text
        else:
            self.progress.append(f"New user request: {text}")

    def add_progress(self, note: str) -> None:
        self.progress.append(note)

    def add_report(self, report: SubAgentReport) -> None:
        self.subagent_reports.append(report)

    def add_source(self, source: SourceRecord) -> None:
        self.sources.append(source)

    def add_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def add_observation(self, note: str) -> None:
        self.observations.append(note)

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "progress": list(self.progress),
            "subagent_reports": [
                {
                    "agent": report.agent,
                    "task": report.task,
                    "summary": report.summary,
                    "success": report.success,
                }
                for report in self.subagent_reports
            ],
            "sources": [
                {"origin": source.origin.value, "reference": source.reference, "detail": source.detail}
                for source in self.sources
            ],
            "files_modified": list(self.files_modified),
            "observations": list(self.observations),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def render(self, max_items: int = 10) -> str:
        """Compact text view for prompts and the /state command."""
        lines = [f"Original request: {self.request or '(none yet)'}"]
        lines.extend(_section("Progress", self.progress, max_items))
        lines.extend(
            _section(
                "Subagent reports",
                [
                    f"{report.agent} ({'ok' if report.success else 'failed'}): {report.summary}"
                    for report in self.subagent_reports
                ],
                max_items,
            )
        )
        lines.extend(
            _section(
                "Sources consulted",
                [f"[{source.origin.value}] {source.reference}" for source in self.sources],
                max_items,
            )
        )
        lines.extend(_section("Files modified", self.files_modified, max_items))
        lines.extend(_section("Observations", self.observations, max_items))
        return "\n".join(lines)


def _section(title: str, items: list[str], max_items: int) -> list[str]:
    if not items:
        return []
    shown = items[-max_items:]
    lines = [f"{title}:"]
    lines.extend(f"- {item}" for item in shown)
    if len(items) > max_items:
        lines.append(f"- ... ({len(items) - max_items} earlier entries omitted)")
    return lines
