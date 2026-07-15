"""Plan mode: before executing tools, negotiate a plan with the user.

Flow: generate a numbered plan with an extra (tool-free) LLM call, show it,
and let the user approve, modify (with feedback → regenerate) or reject it.
Tools only run after approval.
"""

from __future__ import annotations

import logging

from coding_agent.agent.conversation import ConversationHistory
from coding_agent.agent.io import AgentIO
from coding_agent.agent.prompts import PLANNING_INSTRUCTION
from coding_agent.llm import LLMClient
from coding_agent.models import Message, Role

logger = logging.getLogger(__name__)


class Planner:
    def __init__(self, llm: LLMClient, io: AgentIO, enabled: bool = False) -> None:
        self._llm = llm
        self._io = io
        self.enabled = enabled

    def toggle(self, enabled: bool) -> None:
        self.enabled = enabled

    def negotiate(self, history: ConversationHistory) -> bool:
        """Run the plan/approve loop. Returns True when execution may proceed.

        On approval the plan (and the approval) are appended to the history so
        the execution phase follows it. On rejection the history records the
        rejection and False is returned; the harness must not execute anything.
        """
        planning_context: list[Message] = [Message(role=Role.USER, content=PLANNING_INSTRUCTION)]

        while True:
            plan = self._generate_plan(history, planning_context)
            self._io.show_plan(plan)
            choice = self._ask_choice()

            if choice == "a":
                logger.info("Plan approved by user")
                history.add_assistant_text(f"Proposed plan:\n{plan}")
                history.add_user("The plan is approved. Execute it now.")
                return True
            if choice == "r":
                logger.info("Plan rejected by user")
                history.add_assistant_text(f"Proposed plan:\n{plan}")
                history.add_user("The plan was rejected. Do not execute anything.")
                return False
            # modify: capture feedback and regenerate
            feedback = self._io.ask("Describe the changes you want: ")
            logger.info("Plan modification requested")
            planning_context.append(Message(role=Role.ASSISTANT, content=plan))
            planning_context.append(
                Message(role=Role.USER, content=f"Revise the plan with this feedback: {feedback}")
            )

    def _generate_plan(
        self, history: ConversationHistory, planning_context: list[Message]
    ) -> str:
        turn = self._llm.complete(tuple(history.messages()) + tuple(planning_context))
        return turn.text or "(the model returned an empty plan)"

    def _ask_choice(self) -> str:
        while True:
            answer = self._io.ask("Plan: [a]pprove / [m]odify / [r]eject: ").strip().lower()
            if answer in {"a", "m", "r"}:
                return answer
            self._io.detail("Please answer 'a', 'm' or 'r'.")
