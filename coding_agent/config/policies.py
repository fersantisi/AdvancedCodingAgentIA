"""Agent policies: the ``agent.config.json`` permission model (TP Final schema).

Complements the legacy guardrails with per-operation rules validated before
EVERY tool call:

* ``workspace``          — all path arguments must resolve inside it.
* ``permissions.read.deny``  — glob patterns the agent may never read.
* ``permissions.write.deny`` — glob patterns the agent may never modify.
* ``commands.deny``          — forbidden command substrings.
* ``commands.require_approval`` — commands that always need user confirmation,
  even when supervision is toggled off (the config file is the source of truth).

Glob patterns are matched against the workspace-relative POSIX path
(``secrets/**``, ``**/*.pem``, ``.github/**``); patterns without a separator
(``.env``, ``package-lock.json``) also match the bare file name anywhere.
A violation raises :class:`PolicyViolation` (a :class:`GuardrailViolation`
subclass, so the harness turns it into an error tool-result, never a crash).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_agent.config.guardrails import GuardrailViolation

logger = logging.getLogger(__name__)


class PolicyViolation(GuardrailViolation):
    """A tool call was blocked by the agent.config policies."""


@dataclass(frozen=True)
class AgentPolicies:
    """Per-operation restrictions loaded from ``agent.config.json``."""

    workspace: Path | None = None
    read_deny: tuple[str, ...] = ()
    write_deny: tuple[str, ...] = ()
    command_deny: tuple[str, ...] = ()
    command_require_approval: tuple[str, ...] = ()

    @classmethod
    def load(cls, config_path: Path, base_dir: Path | None = None) -> AgentPolicies:
        """Load policies from a JSON file; ``workspace`` resolves against ``base_dir``."""
        base = (base_dir or Path.cwd()).resolve()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise PolicyViolation(f"Agent config file not found: {config_path}") from None
        except json.JSONDecodeError as exc:
            raise PolicyViolation(f"Invalid JSON in {config_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyViolation(f"{config_path} must contain a JSON object")

        permissions = _as_object(data, "permissions")
        commands = _as_object(data, "commands")
        workspace_raw = data.get("workspace")
        if workspace_raw is not None and not isinstance(workspace_raw, str):
            raise PolicyViolation("Policy key 'workspace' must be a string path")

        policies = cls(
            workspace=(base / workspace_raw).resolve() if workspace_raw else None,
            read_deny=_pattern_list(_as_object(permissions, "read"), "deny", "permissions.read.deny"),
            write_deny=_pattern_list(_as_object(permissions, "write"), "deny", "permissions.write.deny"),
            command_deny=_pattern_list(commands, "deny", "commands.deny"),
            command_require_approval=_pattern_list(
                commands, "require_approval", "commands.require_approval"
            ),
        )
        logger.info("Agent policies loaded from %s", config_path)
        return policies

    @classmethod
    def permissive(cls) -> AgentPolicies:
        """No restrictions (used when no agent.config file is configured)."""
        return cls()

    def validate(self, tool_name: str, arguments: Mapping[str, Any], *, read_only: bool) -> None:
        """Check one tool call against the policies before it executes.

        Raises:
            PolicyViolation: with a reason the LLM can understand and adapt to.
        """
        for key in ("path", "working_dir"):
            raw = arguments.get(key)
            if isinstance(raw, str) and raw.strip():
                self._validate_path(raw, read_only=read_only)
        command = arguments.get("command")
        if tool_name == "run_command" and isinstance(command, str):
            self._validate_command(command)

    def approval_required(self, tool_name: str, arguments: Mapping[str, Any]) -> bool:
        """True when the call matches a command that always needs confirmation."""
        command = arguments.get("command")
        if tool_name != "run_command" or not isinstance(command, str):
            return False
        normalized = _normalize(command)
        return any(_normalize(entry) in normalized for entry in self.command_require_approval)

    def _validate_path(self, raw_path: str, *, read_only: bool) -> None:
        resolved = Path(raw_path).resolve()
        relative = self._relative_to_workspace(resolved, raw_path)
        deny_patterns = self.read_deny if read_only else self.write_deny
        operation = "read" if read_only else "modified"
        for pattern in deny_patterns:
            if _matches(pattern, relative, resolved.name):
                raise PolicyViolation(
                    f"'{raw_path}' may not be {operation} (matches policy pattern '{pattern}')"
                )

    def _relative_to_workspace(self, resolved: Path, raw_path: str) -> str:
        if self.workspace is None:
            return resolved.as_posix()
        try:
            return resolved.relative_to(self.workspace).as_posix()
        except ValueError:
            raise PolicyViolation(
                f"'{raw_path}' is outside the configured workspace '{self.workspace}'"
            ) from None

    def _validate_command(self, command: str) -> None:
        normalized = _normalize(command)
        for entry in self.command_deny:
            if _normalize(entry) in normalized:
                raise PolicyViolation(
                    f"Command blocked by policy (matches forbidden pattern '{entry}')"
                )


def _matches(pattern: str, relative_path: str, file_name: str) -> bool:
    if "/" not in pattern and _glob_to_regex(pattern).fullmatch(file_name):
        return True
    return bool(_glob_to_regex(pattern).fullmatch(relative_path))


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob (with ``**`` crossing separators) into a regex.

    ``**/`` also matches zero directories, so ``**/*.pem`` covers ``key.pem``
    and ``secrets/**`` covers everything under ``secrets/``.
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern[i : i + 3] == "**/":
            parts.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif char == "*":
            parts.append("[^/]*")
            i += 1
        elif char == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(char))
            i += 1
    return re.compile("".join(parts))


def _normalize(command: str) -> str:
    return " ".join(command.lower().split())


def _as_object(data: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise PolicyViolation(f"Policy key '{key}' must be a JSON object")
    return value


def _pattern_list(data: Mapping[str, Any], key: str, label: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyViolation(f"Policy key '{label}' must be a list of strings")
    return tuple(value)
