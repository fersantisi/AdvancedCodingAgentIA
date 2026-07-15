"""Agent core: harness (inner loop), conversation, subagents, memory and modes."""

from coding_agent.agent.compaction import ContextCompactor
from coding_agent.agent.conversation import ConversationHistory
from coding_agent.agent.harness import AgentHarness
from coding_agent.agent.loop_detector import LoopDetector
from coding_agent.agent.memory import MEMORY_CATEGORIES, ProjectMemory
from coding_agent.agent.planner import Planner
from coding_agent.agent.subagent import SubAgentRunner, SubAgentSpec, default_specs
from coding_agent.agent.supervisor import Supervisor

__all__ = [
    "MEMORY_CATEGORIES",
    "AgentHarness",
    "ContextCompactor",
    "ConversationHistory",
    "LoopDetector",
    "Planner",
    "ProjectMemory",
    "SubAgentRunner",
    "SubAgentSpec",
    "Supervisor",
    "default_specs",
]
