"""ADK callback factories that enforce a ``RunBudget`` (issue 069 Phase 0).

These build the ``before_tool_callback`` / ``before_model_callback`` to wire onto an
``LlmAgent`` in later phases. They accept ADK's callback arguments generically (``*args`` /
``**kwargs``) so they stay valid across ADK versions and are unit-testable in isolation.

Two layers are intended (issue 069): per-agent callbacks (these) for budget enforcement, and a
Runner ``BasePlugin`` for run-wide event recording (added when the Twin Agent is wired).
"""

import json
from collections.abc import Callable

from service.agents.budget import BudgetExceeded, RunBudget

# Cap any single tool result fed back into the LLM context (~12k chars ≈ 3k tokens). MCP tools
# (Trivy whole-repo scans, GitHub PR/commit JSON, CodeGraphContext queries, Serena/Semgrep results)
# can return very large payloads that then accumulate in the multi-turn conversation history and are
# re-sent on every subsequent model call — inflating each request (cost + 502/timeout risk on the
# Vertex gateway). Truncating oversized results bounds that growth uniformly across all tools.
_MAX_TOOL_RESULT_CHARS = 12_000


def make_before_tool_callback(budget: RunBudget) -> Callable[..., dict[str, object] | None]:
    """Build an ADK ``before_tool_callback`` enforcing the run's tool-call budget.

    Returns a dict — a short-circuit tool result, so ADK skips the actual tool — once the budget
    is exhausted; otherwise ``None`` to let the tool run. The returned callback ignores ADK's
    positional args (``tool``, ``args``, ``tool_context``) generically.
    """

    def before_tool_callback(*_args: object, **_kwargs: object) -> dict[str, object] | None:
        try:
            budget.charge_tool_call()
        except BudgetExceeded as exc:
            return {"error": str(exc), "budget_exceeded": True}
        return None

    return before_tool_callback


def make_before_model_callback(budget: RunBudget) -> Callable[..., None]:
    """Build an ADK ``before_model_callback`` that charges the model-call budget.

    Raises ``BudgetExceeded`` once the cap is passed, aborting the run — a hard stop the LLM
    cannot talk its way past. Returns ``None`` to let the model call proceed.
    """

    def before_model_callback(*_args: object, **_kwargs: object) -> None:
        budget.charge_model_call()
        return None

    return before_model_callback


def make_after_tool_callback() -> Callable[..., dict[str, object] | None]:
    """Build an ADK ``after_tool_callback`` that truncates oversized tool results.

    ADK calls it as ``cb(tool=, args=, tool_context=, tool_response=...)`` and uses a non-``None``
    return to REPLACE the tool result. We return a bounded stand-in only when a result serialises
    beyond ``_MAX_TOOL_RESULT_CHARS`` (so small results pass through unchanged, preserving shape),
    keeping the accumulated conversation context — and thus each model request — from ballooning.
    """

    def after_tool_callback(*_args: object, **kwargs: object) -> dict[str, object] | None:
        response = kwargs.get("tool_response")
        if response is None:
            return None
        try:
            serialized = json.dumps(response, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return None  # not serialisable → leave ADK's original handling untouched
        if len(serialized) <= _MAX_TOOL_RESULT_CHARS:
            return None  # small enough — keep the exact original result
        return {
            "result": serialized[:_MAX_TOOL_RESULT_CHARS] + "\n… (truncated by DevDebtOps to bound agent context)",
            "truncated": True,
            "original_chars": len(serialized),
        }

    return after_tool_callback
