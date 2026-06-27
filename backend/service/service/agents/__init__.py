"""ADK agent foundation (issue 069 Phase 0).

Reusable building blocks for the agentic analysis: Vertex model resolution, event→trace
adaptation, per-run budget guardrails plus the ADK callback factories that enforce them, and
deterministic code-metric tools. Later phases wire these onto ``LlmAgent`` / ``LoopAgent`` /
``AgentTool`` / ``Runner`` and a ``BasePlugin`` for run-wide event recording.
"""

from service.agents.budget import BudgetExceeded, RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import vertex_model_name
from service.agents.trace import event_to_trace, summarize_args

__all__ = [
    "BudgetExceeded",
    "RunBudget",
    "event_to_trace",
    "make_before_model_callback",
    "make_before_tool_callback",
    "summarize_args",
    "vertex_model_name",
]
