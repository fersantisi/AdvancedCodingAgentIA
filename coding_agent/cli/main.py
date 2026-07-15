"""Entry point: composition root and the outer conversation loop.

Run with:  python -m coding_agent.cli.main
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from coding_agent.agent import (
    MEMORY_CATEGORIES,
    AgentHarness,
    ContextCompactor,
    ConversationHistory,
    LoopDetector,
    Planner,
    ProjectMemory,
    SubAgentRunner,
    Supervisor,
)
from coding_agent.agent.prompts import build_system_prompt
from coding_agent.cli.console import ConsoleIO
from coding_agent.config import (
    AgentPolicies,
    Guardrails,
    GuardrailViolation,
    Settings,
    SettingsError,
)
from coding_agent.config.logging_config import setup_logging
from coding_agent.llm import LLMClient, LLMError, create_llm_client
from coding_agent.models import Message, Role, TaskState
from coding_agent.observability import Tracer, create_tracer
from coding_agent.rag.embeddings import NullEmbeddings, OpenAIEmbeddings
from coding_agent.tools import ToolRegistry
from coding_agent.tools.ask_user import AskUserTool
from coding_agent.tools.delegate import DelegateTool
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.rag_search import RagSearchTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.remember import RememberTool
from coding_agent.tools.run_command import RunCommandTool
from coding_agent.tools.web_search import NullSearchProvider, TavilyProvider, WebSearchTool
from coding_agent.tools.write_file import WriteFileTool

logger = logging.getLogger(__name__)

EXIT_COMMANDS = frozenset({"exit", "quit"})

HELP_TEXT = """Commands:
  /plan on|off       Toggle plan mode (plan -> approve/modify/reject -> execute)
  /supervise on|off  Toggle supervision (confirm mutating tools; policy-required
                     approvals always ask, regardless of this toggle)
  /state             Show the shared task state (/state json for raw JSON)
  /memory            Show the persistent project memory
  /status            Show current modes and model
  /tools             List available tools
  /help              Show this help
  exit | quit        Leave the program
Anything else is sent to the agent."""

SESSION_SUMMARY_INSTRUCTION = (
    "The session is ending. Summarize it in at most 5 short lines for the persistent "
    "project memory: what was asked, what was done, key findings or decisions, and "
    "anything left unresolved. Respond with the summary only."
)


@dataclass(frozen=True)
class AgentApp:
    """Everything the outer loop needs, wired once by ``build_app``."""

    harness: AgentHarness
    planner: Planner
    supervisor: Supervisor
    state: TaskState
    memory: ProjectMemory
    registry: ToolRegistry
    llm: LLMClient
    history: ConversationHistory
    tracer: Tracer


def build_registry(
    settings: Settings, state: TaskState, tracer: Tracer, io: ConsoleIO, memory: ProjectMemory
) -> ToolRegistry:
    """Wire up every tool with its configuration (single place to add tools)."""
    search_provider = (
        TavilyProvider(settings.tavily_api_key)
        if settings.tavily_api_key
        else NullSearchProvider()
    )
    embeddings = (
        OpenAIEmbeddings(settings.openai_api_key, model=settings.embeddings_model)
        if settings.openai_api_key
        else NullEmbeddings()
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
            WebSearchTool(search_provider, state=state),
            RagSearchTool(settings.rag_store_path, embeddings, state=state, tracer=tracer),
            RememberTool(memory, MEMORY_CATEGORIES),
            AskUserTool(io),
        ]
    )


def build_app(
    settings: Settings,
    guardrails: Guardrails,
    policies: AgentPolicies,
    io: ConsoleIO,
) -> AgentApp:
    """Composition root: every dependency is created and injected here."""
    tracer = create_tracer(settings)
    llm = create_llm_client(settings, tracer)
    state = TaskState()
    memory = ProjectMemory(settings.memory_file)
    working_dir = Path.cwd()

    registry = build_registry(settings, state, tracer, io, memory)
    supervisor = Supervisor(io, enabled=True)
    planner = Planner(llm, io, enabled=False)

    runner = SubAgentRunner(
        llm=llm,
        registry=registry,
        guardrails=guardrails,
        policies=policies,
        supervisor=supervisor,
        io=io,
        state=state,
        tracer=tracer,
        working_dir=working_dir,
        memory_text=memory.render() if not memory.is_empty() else "",
    )
    registry.register(DelegateTool(runner, runner.roles()))

    history = ConversationHistory(
        build_system_prompt(
            working_dir,
            memory=memory.render() if not memory.is_empty() else "",
            subagents=runner.roles(),
        )
    )
    harness = AgentHarness(
        llm=llm,
        registry=registry,
        history=history,
        guardrails=guardrails,
        supervisor=supervisor,
        planner=planner,
        io=io,
        max_iterations=settings.max_tool_iterations,
        policies=policies,
        state=state,
        tracer=tracer,
        loop_detector=LoopDetector(),
        compactor=ContextCompactor(llm, max_messages=settings.compact_after_messages),
        agent_name="main",
    )
    return AgentApp(
        harness=harness,
        planner=planner,
        supervisor=supervisor,
        state=state,
        memory=memory,
        registry=registry,
        llm=llm,
        history=history,
        tracer=tracer,
    )


def handle_command(line: str, app: AgentApp, settings: Settings, io: ConsoleIO) -> None:
    parts = line.lower().split()
    command, argument = parts[0], parts[1] if len(parts) > 1 else None

    if command == "/help":
        io.info(HELP_TEXT)
    elif command == "/status":
        io.info(
            f"model: {settings.openai_model} | plan mode: {'on' if app.planner.enabled else 'off'} "
            f"| supervision: {'on' if app.supervisor.enabled else 'off'} "
            f"| observability: {settings.observability_provider}"
        )
    elif command == "/tools":
        io.info("Available tools: " + ", ".join(app.registry.names()))
    elif command == "/state":
        io.info(app.state.to_json() if argument == "json" else app.state.render())
    elif command == "/memory":
        io.info(app.memory.render())
    elif command == "/plan" and argument in ("on", "off"):
        app.planner.toggle(argument == "on")
        io.info(f"plan mode: {argument}")
    elif command == "/supervise" and argument in ("on", "off"):
        app.supervisor.toggle(argument == "on")
        io.info(f"supervision: {argument}")
    else:
        io.warn(f"Unknown command: {line} — type /help")


def run_conversation_loop(app: AgentApp, settings: Settings, io: ConsoleIO) -> None:
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
            save_session_summary(app, io)
            app.tracer.flush()
            io.info("Goodbye!")
            return
        if line.startswith("/"):
            handle_command(line, app, settings, io)
            continue

        app.state.record_request(line)
        try:
            response = app.harness.run_turn(line)
        except KeyboardInterrupt:
            io.warn("\nTurn cancelled by user.")
            continue
        except LLMError as error:
            io.error(f"LLM failure: {error}")
            continue
        io.assistant(response)


def save_session_summary(app: AgentApp, io: ConsoleIO) -> None:
    """Persist a short LLM-written summary of the session to project memory."""
    if len(app.history) <= 1:  # only the system prompt: nothing happened
        return
    try:
        turn = app.llm.complete(
            app.history.messages()
            + (Message(role=Role.USER, content=SESSION_SUMMARY_INSTRUCTION),)
        )
    except LLMError as error:
        io.warn(f"Could not summarize the session for memory: {error}")
        return
    if turn.text:
        today = datetime.date.today().isoformat()
        app.memory.add_session_summary(f"[{today}] {turn.text.strip()}")
        io.detail("(session summary saved to project memory)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coding Agent — LLM tool-use harness")
    parser.add_argument(
        "--guardrails",
        type=Path,
        default=Path("guardrails.json"),
        help="Path to the guardrails JSON file (default: guardrails.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("agent.config.json"),
        help="Path to the agent policies file (default: agent.config.json)",
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

    try:
        if args.guardrails.exists():
            guardrails = Guardrails.load(args.guardrails)
        else:
            guardrails = Guardrails.permissive()
            io.warn(f"No guardrails file at '{args.guardrails}' — legacy guardrails disabled.")
        if args.config.exists():
            policies = AgentPolicies.load(args.config)
        else:
            policies = AgentPolicies.permissive()
            io.warn(f"No agent config at '{args.config}' — running without agent policies.")
    except GuardrailViolation as error:
        io.error(f"Configuration error: {error}")
        return 1

    try:
        app = build_app(settings, guardrails, policies, io)
    except SettingsError as error:
        io.error(f"Configuration error: {error}")
        return 1

    io.banner(settings.openai_model, app.planner.enabled, app.supervisor.enabled)
    run_conversation_loop(app, settings, io)
    return 0


if __name__ == "__main__":
    sys.exit(main())
