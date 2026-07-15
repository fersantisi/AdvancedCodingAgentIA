"""Entry point: composition root and the outer conversation loop.

Run with:  python -m coding_agent.cli.main
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from coding_agent.agent import AgentHarness, ConversationHistory, Planner, Supervisor
from coding_agent.agent.prompts import build_system_prompt
from coding_agent.cli.console import ConsoleIO
from coding_agent.config import Guardrails, GuardrailViolation, Settings, SettingsError
from coding_agent.config.logging_config import setup_logging
from coding_agent.llm import LLMError, create_llm_client
from coding_agent.tools import ToolRegistry
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.run_command import RunCommandTool
from coding_agent.tools.web_search import NullSearchProvider, TavilyProvider, WebSearchTool
from coding_agent.tools.write_file import WriteFileTool

logger = logging.getLogger(__name__)

EXIT_COMMANDS = frozenset({"exit", "quit"})

HELP_TEXT = """Commands:
  /plan on|off       Toggle plan mode (plan -> approve/modify/reject -> execute)
  /supervise on|off  Toggle supervision (confirm write_file / run_command)
  /status            Show current modes and model
  /tools             List available tools
  /help              Show this help
  exit | quit        Leave the program
Anything else is sent to the agent."""


def build_registry(settings: Settings) -> ToolRegistry:
    """Wire up every tool with its configuration (single place to add tools)."""
    search_provider = (
        TavilyProvider(settings.tavily_api_key)
        if settings.tavily_api_key
        else NullSearchProvider()
    )
    return ToolRegistry(
        [
            ReadFileTool(max_output_chars=settings.max_read_file_chars),
            WriteFileTool(),
            ListFilesTool(),
            RunCommandTool(
                timeout_seconds=settings.command_timeout_seconds,
                max_output_chars=settings.max_tool_output_chars,
            ),
            WebSearchTool(search_provider),
        ]
    )


def build_harness(
    settings: Settings, guardrails: Guardrails, io: ConsoleIO
) -> tuple[AgentHarness, Planner, Supervisor]:
    """Composition root: every dependency is created and injected here."""
    llm = create_llm_client(settings)
    registry = build_registry(settings)
    history = ConversationHistory(build_system_prompt(Path.cwd()))
    planner = Planner(llm, io, enabled=False)
    supervisor = Supervisor(io, enabled=True)
    harness = AgentHarness(
        llm=llm,
        registry=registry,
        history=history,
        guardrails=guardrails,
        supervisor=supervisor,
        planner=planner,
        io=io,
        max_iterations=settings.max_tool_iterations,
    )
    return harness, planner, supervisor


def handle_command(
    line: str,
    planner: Planner,
    supervisor: Supervisor,
    settings: Settings,
    io: ConsoleIO,
) -> None:
    parts = line.lower().split()
    command, argument = parts[0], parts[1] if len(parts) > 1 else None

    if command == "/help":
        io.info(HELP_TEXT)
    elif command == "/status":
        io.info(
            f"model: {settings.openai_model} | plan mode: {'on' if planner.enabled else 'off'} "
            f"| supervision: {'on' if supervisor.enabled else 'off'}"
        )
    elif command == "/tools":
        io.info("Available tools: read_file, write_file, list_files, run_command, web_search")
    elif command == "/plan" and argument in ("on", "off"):
        planner.toggle(argument == "on")
        io.info(f"plan mode: {argument}")
    elif command == "/supervise" and argument in ("on", "off"):
        supervisor.toggle(argument == "on")
        io.info(f"supervision: {argument}")
    else:
        io.warn(f"Unknown command: {line} — type /help")


def run_conversation_loop(
    harness: AgentHarness,
    planner: Planner,
    supervisor: Supervisor,
    settings: Settings,
    io: ConsoleIO,
) -> None:
    """The outer loop: wait for input, run one agent turn, print the response."""
    while True:
        try:
            line = io.read_user_input()
        except KeyboardInterrupt:
            io.info("\n(type 'exit' or 'quit' to leave)")
            continue

        if not line:
            continue
        if line.lower() in EXIT_COMMANDS:
            io.info("Goodbye!")
            return
        if line.startswith("/"):
            handle_command(line, planner, supervisor, settings, io)
            continue

        try:
            response = harness.run_turn(line)
        except KeyboardInterrupt:
            io.warn("\nTurn cancelled by user.")
            continue
        except LLMError as error:
            io.error(f"LLM failure: {error}")
            continue
        io.assistant(response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coding Agent — LLM tool-use harness")
    parser.add_argument(
        "--guardrails",
        type=Path,
        default=Path("guardrails.json"),
        help="Path to the guardrails JSON file (default: guardrails.json)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show INFO logs on the console")
    args = parser.parse_args(argv)

    io = ConsoleIO()

    try:
        settings = Settings.from_env()
        settings.validate()
    except SettingsError as error:
        io.error(f"Configuration error: {error}")
        return 1

    setup_logging(settings.log_file, verbose=args.verbose)

    if args.guardrails.exists():
        try:
            guardrails = Guardrails.load(args.guardrails)
        except GuardrailViolation as error:
            io.error(f"Guardrails error: {error}")
            return 1
    else:
        guardrails = Guardrails.permissive()
        io.warn(f"No guardrails file at '{args.guardrails}' — running without restrictions.")

    harness, planner, supervisor = build_harness(settings, guardrails, io)
    io.banner(settings.openai_model, planner.enabled, supervisor.enabled)
    run_conversation_loop(harness, planner, supervisor, settings, io)
    return 0


if __name__ == "__main__":
    sys.exit(main())
