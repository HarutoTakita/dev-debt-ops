"""ADK agent foundation (issue 069 Phase 0).

Reusable building blocks for the agentic analysis: Vertex model resolution, event→trace
adaptation, per-run budget guardrails plus the ADK callback factories that enforce them, and
deterministic code-metric tools. Later phases wire these onto ``LlmAgent`` / ``LoopAgent`` /
``AgentTool`` / ``Runner`` and a ``BasePlugin`` for run-wide event recording.
"""

from service.agents.budget import BudgetExceeded, RunBudget
from service.agents.hooks import (
    make_after_tool_callback,
    make_before_model_callback,
    make_before_tool_callback,
)
from service.agents.model import vertex_model_name
from service.agents.plugin import SecretRedactionPlugin, TraceRecorderPlugin
from service.agents.single_agent import run_single_agent
from service.agents.trace import event_to_trace, summarize_args

__all__ = [
    "BudgetExceeded",
    "RunBudget",
    "SecretRedactionPlugin",
    "TraceRecorderPlugin",
    "event_to_trace",
    "make_after_tool_callback",
    "make_before_model_callback",
    "make_before_tool_callback",
    "run_single_agent",
    "summarize_args",
    "vertex_model_name",
]
