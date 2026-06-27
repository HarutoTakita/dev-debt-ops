"""ADK callback factories that enforce a ``RunBudget`` (issue 069 Phase 0).

These build the ``before_tool_callback`` / ``before_model_callback`` to wire onto an
``LlmAgent`` in later phases. They accept ADK's callback arguments generically (``*args`` /
``**kwargs``) so they stay valid across ADK versions and are unit-testable in isolation.

Two layers are intended (issue 069): per-agent callbacks (these) for budget enforcement, and a
Runner ``BasePlugin`` for run-wide event recording (added when the Twin Agent is wired).
"""

from collections.abc import Callable

from service.agents.budget import BudgetExceeded, RunBudget


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
