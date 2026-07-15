"""The harness: the inner tool-execution loop of the agent.

``run_turn`` handles exactly one user message: it calls the LLM, executes any
requested tools (validated by guardrails and agent policies and, when enabled
or required by policy, approved by the supervisor), feeds results back, and
repeats until the LLM answers without tool calls. The outer conversation loop
lives in the CLI and only calls ``run_turn`` — the two loops are fully
independent.

The same class powers the orchestrator and every subagent (each with its own
registry, history and iteration cap); they share the task state, the tracer
and the policy configuration.
"""

from __future__ import annotations

import logging
import time

from coding_agent.agent.compaction import ContextCompactor
from coding_agent.agent.conversation import ConversationHistory
from coding_agent.agent.io import AgentIO
from coding_agent.agent.loop_detector import NUDGE_MESSAGE, LoopDetector, LoopVerdict
from coding_agent.agent.planner import Planner
from coding_agent.agent.supervisor import Supervisor
from coding_agent.config.guardrails import Guardrails, GuardrailViolation
from coding_agent.config.policies import AgentPolicies, PolicyViolation
from coding_agent.llm import LLMClient
from coding_agent.models import TaskState, ToolCall, ToolResult
from coding_agent.observability.base import NullTracer, Tracer
from coding_agent.tools import ToolError, ToolRegistry
from coding_agent.utils import truncate

logger = logging.getLogger(__name__)

PLAN_REJECTED_MESSAGE = "Plan rejected — no actions were executed. Tell me how to proceed."

_TRACE_PREVIEW_CHARS = 500


class AgentHarness:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        history: ConversationHistory,
        guardrails: Guardrails,
        supervisor: Supervisor,
        planner: Planner,
        io: AgentIO,
        max_iterations: int = 30,
        policies: AgentPolicies | None = None,
        state: TaskState | None = None,
        tracer: Tracer | None = None,
        loop_detector: LoopDetector | None = None,
        compactor: ContextCompactor | None = None,
        agent_name: str = "main",
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._history = history
        self._guardrails = guardrails
        self._supervisor = supervisor
        self._planner = planner
        self._io = io
        self._max_iterations = max_iterations
        self._policies = policies or AgentPolicies.permissive()
        self._state = state
        self._tracer = tracer or NullTracer()
        self._loop_detector = loop_detector
        self._compactor = compactor
        self._agent_name = agent_name

    def run_turn(self, user_input: str) -> str:
        """Process one user message and return the assistant's final text."""
        self._history.add_user(user_input)
        self._tracer.start_turn(self._agent_name, user_input)
        if self._compactor is not None:
            self._compactor.compact_if_needed(self._history)
        if self._loop_detector is not None:
            self._loop_detector.reset()

        if self._planner.enabled and not self._planner.negotiate(self._history):
            return self._finish(PLAN_REJECTED_MESSAGE, iterations=0)

        for iteration in range(1, self._max_iterations + 1):
            turn = self._llm.complete(self._history.messages(), self._registry.specs())
            self._history.add_assistant(turn)

            if not turn.wants_tools:
                logger.info("Turn finished after %d inner-loop iteration(s)", iteration)
                self._io.detail(f"(inner loop iterations: {iteration})")
                return self._finish(
                    turn.text or "(the model returned an empty response)", iterations=iteration
                )

            if turn.text:
                self._io.detail(turn.text)
            if self._run_tool_batch(turn.tool_calls):
                summary = self._loop_detector.abort_summary()  # type: ignore[union-attr]
                if self._state is not None:
                    self._state.add_observation(
                        f"{self._agent_name}: turn aborted by loop detection"
                    )
                return self._finish(summary, iterations=iteration)

        logger.warning("Inner loop stopped: hit max_iterations=%d", self._max_iterations)
        return self._finish(
            f"Stopped after {self._max_iterations} tool iterations without finishing. "
            "Ask me to continue if you want me to keep going.",
            iterations=self._max_iterations,
        )

    def _run_tool_batch(self, calls: tuple[ToolCall, ...]) -> bool:
        """Execute one assistant turn's tool calls. Returns True to abort the turn.

        Every result is appended before reacting to loop verdicts so the
        history never leaves a tool request without its result.
        """
        nudge = False
        abort = False
        for call in calls:
            result = self._execute_call(call)
            self._history.add_tool_result(result)
            if self._loop_detector is None:
                continue
            verdict = self._loop_detector.record(call, result)
            nudge = nudge or verdict is LoopVerdict.WARN
            abort = abort or verdict is LoopVerdict.ABORT
        if nudge and not abort:
            self._history.add_user(NUDGE_MESSAGE)
            self._io.detail("(loop detected — asked the agent to change strategy)")
        return abort

    def _finish(self, final_text: str, iterations: int) -> str:
        self._tracer.end_turn(self._agent_name, final_text, iterations)
        return final_text

    def _execute_call(self, call: ToolCall) -> ToolResult:
        """Run one tool call through guardrails, policies, supervision and execution.

        Every failure mode becomes an error ToolResult so the LLM can adapt;
        this method never raises.
        """
        self._io.show_tool_call(call.name, call.arguments)
        logger.info("Tool call: %s(%s)", call.name, call.arguments)
        started = time.monotonic()

        try:
            tool = self._registry.get(call.name)
            self._guardrails.validate(call.name, call.arguments)
            self._policies.validate(call.name, call.arguments, read_only=tool.read_only)
        except PolicyViolation as violation:
            return self._error_result(call, f"Blocked by policy: {violation}", started)
        except GuardrailViolation as violation:
            return self._error_result(call, f"Blocked by guardrails: {violation}", started)
        except ToolError as error:
            return self._error_result(call, str(error), started)

        required = self._policies.approval_required(call.name, call.arguments)
        if not self._supervisor.approve(tool, call, required=required):
            return self._error_result(
                call, "Denied by the user. Do not retry the same action.", started
            )

        try:
            output = tool.execute(call.arguments)
        except ToolError as error:
            return self._error_result(call, str(error), started)
        except Exception:  # noqa: BLE001 — a buggy tool must not kill the loop
            logger.exception("Unexpected error in tool %s", call.name)
            return self._error_result(
                call, f"Unexpected internal error in tool '{call.name}'", started
            )

        self._io.show_tool_result(output, is_error=False)
        self._record_tool(call, output, is_error=False, started=started)
        if self._state is not None and not tool.read_only:
            path = call.arguments.get("path")
            if isinstance(path, str) and path.strip():
                self._state.add_file_modified(path)
        return ToolResult(tool_call_id=call.id, content=output)

    def _error_result(self, call: ToolCall, message: str, started: float) -> ToolResult:
        logger.info("Tool %s failed: %s", call.name, message)
        self._io.show_tool_result(message, is_error=True)
        self._record_tool(call, message, is_error=True, started=started)
        if self._state is not None:
            self._state.add_observation(f"{call.name} failed: {truncate(message, 200)}")
        return ToolResult(tool_call_id=call.id, content=message, is_error=True)

    def _record_tool(self, call: ToolCall, output: str, *, is_error: bool, started: float) -> None:
        self._tracer.record_tool_call(
            name=call.name,
            arguments=call.arguments,
            output_preview=truncate(output, _TRACE_PREVIEW_CHARS),
            is_error=is_error,
            latency_seconds=time.monotonic() - started,
        )
