"""Subagents: specialized agents the orchestrator delegates work to.

Each subagent is the same :class:`AgentHarness` machinery with its own
restricted tool registry, its own fresh conversation per delegation and a
specialized system prompt — while sharing the task state, policies,
supervisor, tracer and LLM client with the orchestrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from coding_agent.agent.conversation import ConversationHistory
from coding_agent.agent.harness import AgentHarness
from coding_agent.agent.io import AgentIO
from coding_agent.agent.loop_detector import LoopDetector
from coding_agent.agent.planner import Planner
from coding_agent.agent.prompts import build_subagent_prompt
from coding_agent.agent.supervisor import Supervisor
from coding_agent.config.guardrails import Guardrails
from coding_agent.config.policies import AgentPolicies
from coding_agent.llm import LLMClient
from coding_agent.models import SubAgentReport, TaskState
from coding_agent.observability.base import Tracer
from coding_agent.tools import ToolRegistry
from coding_agent.utils import truncate

logger = logging.getLogger(__name__)

_REPORT_SUMMARY_CHARS = 800


@dataclass(frozen=True)
class SubAgentSpec:
    """Identity of one subagent: responsibility, prompt and allowed tools."""

    name: str
    role: str  # one line, shown to the orchestrator in the delegate tool
    mission: str  # detailed responsibility, injected into the subagent's prompt
    tool_names: tuple[str, ...]
    max_iterations: int = 15


def default_specs() -> dict[str, SubAgentSpec]:
    """The five subagents required by the assignment."""
    specs = (
        SubAgentSpec(
            name="explorer",
            role="Understands the repository: structure, architecture, dependencies, conventions and relevant files.",
            mission=(
                "Your mission is to understand the repository under analysis: its structure, "
                "architecture, dependencies, conventions and which files are relevant to the "
                "current task. Read and list files, run read-oriented commands (git log, grep, "
                "find), and report what you learned — never modify anything."
            ),
            tool_names=("read_file", "list_files", "run_command"),
        ),
        SubAgentSpec(
            name="researcher",
            role="Finds information in the RAG documentation index and, as a fallback, on the web.",
            mission=(
                "Your mission is to find technical information. Query the RAG documentation "
                "index (rag_search) FIRST; only when it lacks sufficient evidence, fall back "
                "to web_search, preferring official documentation. Cite every source you used "
                "and say which fragments supported each claim."
            ),
            tool_names=("rag_search", "web_search", "read_file"),
        ),
        SubAgentSpec(
            name="implementer",
            role="Proposes or applies code changes based on the available findings.",
            mission=(
                "Your mission is to propose or apply code changes based on the findings in the "
                "shared task state. Read the relevant files first, make minimal focused edits, "
                "and report exactly which files you changed and why."
            ),
            tool_names=("read_file", "list_files", "write_file", "run_command"),
        ),
        SubAgentSpec(
            name="tester",
            role="Validates the result by running checks: tests, build, lint or other verifications.",
            mission=(
                "Your mission is to validate the current state of the work by running the "
                "checks that apply to this project (tests, build, lint, running the program). "
                "Report each command you ran, its exit code and the relevant output."
            ),
            tool_names=("run_command", "read_file", "list_files"),
        ),
        SubAgentSpec(
            name="reviewer",
            role="Reviews the diff/changes and validates that they answer the user's request.",
            mission=(
                "Your mission is to review the changes made so far (use git diff and read the "
                "modified files listed in the shared task state) and validate that they answer "
                "the user's original request. Point out problems, omissions or risks; do not "
                "fix them yourself."
            ),
            tool_names=("read_file", "list_files", "run_command"),
        ),
    )
    return {spec.name: spec for spec in specs}


class SubAgentRunner:
    """Builds and runs a one-shot harness for each delegation."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        guardrails: Guardrails,
        policies: AgentPolicies,
        supervisor: Supervisor,
        io: AgentIO,
        state: TaskState,
        tracer: Tracer,
        working_dir: Path,
        specs: dict[str, SubAgentSpec] | None = None,
        memory_text: str = "",
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._guardrails = guardrails
        self._policies = policies
        self._supervisor = supervisor
        self._io = io
        self._state = state
        self._tracer = tracer
        self._working_dir = working_dir
        self._specs = specs if specs is not None else default_specs()
        self._memory_text = memory_text

    def roles(self) -> dict[str, str]:
        """Subagent name -> one-line role (for the delegate tool description)."""
        return {spec.name: spec.role for spec in self._specs.values()}

    def run(self, agent: str, task: str) -> str:
        """Delegate one task to a subagent and return its final report.

        Raises:
            KeyError: if ``agent`` is not a known subagent name.
        """
        spec = self._specs[agent]
        logger.info("Delegating to %s: %s", agent, task)
        self._io.detail(f"[{agent}] task: {task}")

        history = ConversationHistory(
            build_subagent_prompt(
                spec.name,
                spec.mission,
                self._working_dir,
                self._state.render(),
                self._memory_text,
            )
        )
        harness = AgentHarness(
            llm=self._llm,
            registry=self._registry.subset(spec.tool_names),
            history=history,
            guardrails=self._guardrails,
            supervisor=self._supervisor,
            planner=Planner(self._llm, self._io, enabled=False),
            io=self._io,
            max_iterations=spec.max_iterations,
            policies=self._policies,
            state=self._state,
            tracer=self._tracer,
            loop_detector=LoopDetector(),
            agent_name=spec.name,
        )
        result = harness.run_turn(task)
        self._state.add_report(
            SubAgentReport(agent=agent, task=task, summary=truncate(result, _REPORT_SUMMARY_CHARS))
        )
        return result
