"""Common tool interface and registry.

Every tool declares its name, description, JSON-Schema parameters and
whether it is read-only (read-only tools are exempt from supervision).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from coding_agent.models import ToolSpec


class ToolError(Exception):
    """Raised by tools on expected failures (missing file, timeout, ...).

    The harness converts these into error tool-results for the LLM
    instead of crashing the loop.
    """


class UnknownToolError(ToolError):
    """The LLM requested a tool that is not registered."""


class Tool(ABC):
    """Contract every tool must fulfil."""

    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> str:
        """Run the tool and return its textual output.

        Raises:
            ToolError: on any expected failure, with a message the LLM can act on.
        """

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)


def require_string(arguments: dict[str, Any], key: str) -> str:
    """Fetch a mandatory string argument, with a clear error for the LLM."""
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"Missing or invalid required argument '{key}' (expected a non-empty string)")
    return value


class ToolRegistry:
    """Holds the available tools and exposes their specs to the LLM."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(
                f"Unknown tool '{name}'. Available tools: {available}"
            ) from None

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tools.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)
