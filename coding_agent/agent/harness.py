"""The harness: the inner tool-execution loop of the agent.

``run_turn`` handles exactly one user message: it calls the LLM, executes any
requested tools (validated by guardrails and, when enabled, approved by the
supervisor), feeds results back, and repeats until the LLM answers without
tool calls. The outer conversation loop lives in the CLI and only calls
``run_turn`` — the two loops are fully independent.
"""

from __future__ import annotations

import logging

from coding_agent.agent.conversation import ConversationHistory
from coding_agent.agent.io import AgentIO
from coding_agent.agent.planner import Planner
from coding_agent.agent.supervisor import Supervisor
from coding_agent.config.guardrails import Guardrails, GuardrailViolation
from coding_agent.llm import LLMClient
from coding_agent.models import ToolCall, ToolResult
from coding_agent.tools import ToolError, ToolRegistry

logger = logging.getLogger(__name__)

PLAN_REJECTED_MESSAGE = "Plan rejected — no actions were executed. Tell me how to proceed."


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
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._history = history
        self._guardrails = guardrails
        self._supervisor = supervisor
        self._planner = planner
        self._io = io
        self._max_iterations = max_iterations

    def run_turn(self, user_input: str) -> str:
        """Process one user message and return the assistant's final text."""
        self._history.add_user(user_input)

        if self._planner.enabled and not self._planner.negotiate(self._history):
            return PLAN_REJECTED_MESSAGE

        for iteration in range(1, self._max_iterations + 1):
            turn = self._llm.complete(self._history.messages(), self._registry.specs())
            self._history.add_assistant(turn)

            if not turn.wants_tools:
                logger.info("Turn finished after %d inner-loop iteration(s)", iteration)
                self._io.detail(f"(inner loop iterations: {iteration})")
                return turn.text or "(the model returned an empty response)"

            if turn.text:
                self._io.detail(turn.text)
            for call in turn.tool_calls:
                result = self._execute_call(call)
                self._history.add_tool_result(result)

        logger.warning("Inner loop stopped: hit max_iterations=%d", self._max_iterations)
        return (
            f"Stopped after {self._max_iterations} tool iterations without finishing. "
            "Ask me to continue if you want me to keep going."
        )

    def _execute_call(self, call: ToolCall) -> ToolResult:
        """Run one tool call through guardrails, supervision and execution.

        Every failure mode becomes an error ToolResult so the LLM can adapt;
        this method never raises.
        """
        self._io.show_tool_call(call.name, call.arguments)
        logger.info("Tool call: %s(%s)", call.name, call.arguments)

        try:
            tool = self._registry.get(call.name)
            self._guardrails.validate(call.name, call.arguments)
        except GuardrailViolation as violation:
            return self._error_result(call, f"Blocked by guardrails: {violation}")
        except ToolError as error:
            return self._error_result(call, str(error))

        if not self._supervisor.approve(tool, call):
            return self._error_result(call, "Denied by the user. Do not retry the same action.")

        try:
            output = tool.execute(call.arguments)
        except ToolError as error:
            return self._error_result(call, str(error))
        except Exception:  # noqa: BLE001 — a buggy tool must not kill the loop
            logger.exception("Unexpected error in tool %s", call.name)
            return self._error_result(call, f"Unexpected internal error in tool '{call.name}'")

        self._io.show_tool_result(output, is_error=False)
        return ToolResult(tool_call_id=call.id, content=output)

    def _error_result(self, call: ToolCall, message: str) -> ToolResult:
        logger.info("Tool %s failed: %s", call.name, message)
        self._io.show_tool_result(message, is_error=True)
        return ToolResult(tool_call_id=call.id, content=message, is_error=True)
