"""Guardrails: config-file-driven restrictions validated before every tool call.

Loaded once at startup from ``guardrails.json``. The harness calls
``validate()`` for each tool call; a violation becomes an error tool-result
for the LLM (never a crash).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailViolation(Exception):
    """A tool call was blocked by the guardrails configuration."""


@dataclass(frozen=True)
class Guardrails:
    """Restrictions on which paths and commands the agent may touch.

    * ``allowed_directories`` — if non-empty, every path argument must resolve
      inside one of them.
    * ``blocked_directories`` — paths inside these are always rejected.
    * ``blocked_files`` — file names (e.g. ``.env``) or specific paths.
    * ``blocked_commands`` — substrings that make a command rejected
      (whitespace-normalized, case-insensitive).
    """

    allowed_directories: tuple[Path, ...] = ()
    blocked_directories: tuple[Path, ...] = ()
    blocked_files: tuple[str, ...] = ()
    blocked_commands: tuple[str, ...] = ()

    @classmethod
    def load(cls, config_path: Path, base_dir: Path | None = None) -> Guardrails:
        """Load guardrails from a JSON file; relative paths resolve against ``base_dir``."""
        base = (base_dir or Path.cwd()).resolve()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise GuardrailViolation(f"Guardrails file not found: {config_path}") from None
        except json.JSONDecodeError as exc:
            raise GuardrailViolation(f"Invalid JSON in {config_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise GuardrailViolation(f"{config_path} must contain a JSON object")

        guardrails = cls(
            allowed_directories=_as_paths(data, "allowed_directories", base),
            blocked_directories=_as_paths(data, "blocked_directories", base),
            blocked_files=tuple(_as_strings(data, "blocked_files")),
            blocked_commands=tuple(_as_strings(data, "blocked_commands")),
        )
        logger.info("Guardrails loaded from %s", config_path)
        return guardrails

    @classmethod
    def permissive(cls) -> Guardrails:
        """No restrictions (used when no guardrails file is configured)."""
        return cls()

    def validate(self, tool_name: str, arguments: Mapping[str, Any]) -> None:
        """Check one tool call against the rules.

        Raises:
            GuardrailViolation: with a reason the LLM can understand and adapt to.
        """
        path_argument = arguments.get("path")
        if isinstance(path_argument, str) and path_argument.strip():
            self._validate_path(path_argument)
        working_dir = arguments.get("working_dir")
        if isinstance(working_dir, str) and working_dir.strip():
            self._validate_path(working_dir)
        command = arguments.get("command")
        if tool_name == "run_command" and isinstance(command, str):
            self._validate_command(command)

    def _validate_path(self, raw_path: str) -> None:
        resolved = Path(raw_path).resolve()
        for blocked in self.blocked_directories:
            if resolved == blocked or resolved.is_relative_to(blocked):
                raise GuardrailViolation(
                    f"Access to '{raw_path}' is blocked (inside blocked directory '{blocked}')"
                )
        for blocked_file in self.blocked_files:
            if _matches_blocked_file(resolved, blocked_file):
                raise GuardrailViolation(
                    f"Access to '{raw_path}' is blocked (matches blocked file '{blocked_file}')"
                )
        if self.allowed_directories and not any(
            resolved == allowed or resolved.is_relative_to(allowed)
            for allowed in self.allowed_directories
        ):
            allowed_list = ", ".join(str(directory) for directory in self.allowed_directories)
            raise GuardrailViolation(
                f"Access to '{raw_path}' is outside the allowed directories: {allowed_list}"
            )

    def _validate_command(self, command: str) -> None:
        normalized = _normalize(command)
        for blocked in self.blocked_commands:
            if _normalize(blocked) in normalized:
                raise GuardrailViolation(
                    f"Command blocked by guardrails (matches forbidden pattern '{blocked}')"
                )


def _matches_blocked_file(resolved: Path, blocked_entry: str) -> bool:
    if any(separator in blocked_entry for separator in ("/", "\\")):
        return resolved == Path(blocked_entry).resolve()
    return resolved.name == blocked_entry


def _normalize(command: str) -> str:
    return " ".join(command.lower().split())


def _as_paths(data: dict[str, Any], key: str, base: Path) -> tuple[Path, ...]:
    return tuple((base / entry).resolve() for entry in _as_strings(data, key))


def _as_strings(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise GuardrailViolation(f"Guardrails key '{key}' must be a list of strings")
    return value
