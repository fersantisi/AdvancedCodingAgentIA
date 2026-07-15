"""Terminal implementation of the agent's I/O.

Implements the ``AgentIO`` protocol plus the CLI-only concerns
(user prompt, assistant rendering, banner). All printing goes through
this class so the rest of the code never touches ``print``/``input``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from coding_agent.utils import truncate

_PREVIEW_LIMIT = 200


class _Style:
    """Minimal ANSI styling, disabled automatically on non-TTY output."""

    def __init__(self) -> None:
        self._enabled = sys.stdout.isatty()
        if self._enabled and os.name == "nt":
            os.system("")  # enables ANSI escape processing in the Windows console

    def paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self._enabled else text

    def dim(self, text: str) -> str:
        return self.paint(text, "2")

    def cyan(self, text: str) -> str:
        return self.paint(text, "36")

    def yellow(self, text: str) -> str:
        return self.paint(text, "33")

    def red(self, text: str) -> str:
        return self.paint(text, "31")

    def green(self, text: str) -> str:
        return self.paint(text, "32")


class ConsoleIO:
    """Console front-end; satisfies ``coding_agent.agent.io.AgentIO``."""

    def __init__(self) -> None:
        self._style = _Style()

    # ---- CLI-specific -------------------------------------------------

    def banner(self, model: str, plan_enabled: bool, supervision_enabled: bool) -> None:
        print(self._style.cyan("Coding Agent") + f" — model: {model}")
        print(
            f"plan mode: {_on_off(plan_enabled)} | supervision: {_on_off(supervision_enabled)} "
            "| /help for commands | exit/quit to leave"
        )

    def read_user_input(self) -> str:
        try:
            return input(self._style.green(">> ")).strip()
        except EOFError:
            return "exit"

    def assistant(self, text: str) -> None:
        print(f"\n{self._style.cyan('Assistant:')}\n{text}\n")

    def info(self, text: str) -> None:
        print(text)

    def warn(self, text: str) -> None:
        print(self._style.yellow(text))

    def error(self, text: str) -> None:
        print(self._style.red(text))

    # ---- AgentIO protocol ---------------------------------------------

    def confirm(self, question: str) -> bool:
        try:
            answer = input(self._style.yellow(question)).strip().lower()
        except EOFError:
            return False
        return answer in ("", "y", "yes")

    def ask(self, prompt: str) -> str:
        try:
            return input(self._style.yellow(prompt)).strip()
        except EOFError:
            return ""

    def show_plan(self, plan: str) -> None:
        print(f"\n{self._style.cyan('Proposed plan:')}\n{plan}\n")

    def show_tool_call(self, name: str, arguments: dict[str, Any]) -> None:
        rendered = truncate(json.dumps(arguments, ensure_ascii=False), _PREVIEW_LIMIT)
        print(self._style.dim(f"  -> {name} {rendered}"))

    def show_tool_result(self, content: str, is_error: bool) -> None:
        preview = truncate(content.replace("\n", " | "), _PREVIEW_LIMIT)
        if is_error:
            print(self._style.red(f"  <- error: {preview}"))
        else:
            print(self._style.dim(f"  <- {preview}"))

    def detail(self, text: str) -> None:
        print(self._style.dim(f"  {text}"))


def _on_off(enabled: bool) -> str:
    return "on" if enabled else "off"
