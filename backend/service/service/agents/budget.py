"""Per-run budget guardrails for agentic analysis (issue 069 Phase 0).

A ``RunBudget`` tracks tool calls / model calls / files read for one agent run and raises
``BudgetExceeded`` once a cap is passed. It is the cost / runaway-protection core that the ADK
callbacks in ``service.agents.hooks`` enforce, so the framework bounds the run mechanically —
independent of the LLM's own behaviour.
"""

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when an agent run exceeds a configured budget (tool / model / file caps)."""


@dataclass
class RunBudget:
    """Mutable guardrail counters for a single agentic-analysis run.

    Caps default to conservative MVP values; tune per pipeline. The ``charge_*`` methods both
    count and enforce — call them from the ADK callbacks so exceeding a cap stops the run.
    """

    max_tool_calls: int = 80
    max_model_calls: int = 60
    max_files: int = 200
    tool_calls: int = 0
    model_calls: int = 0
    files_read: int = 0

    def charge_tool_call(self) -> None:
        """Count one tool call; raise ``BudgetExceeded`` once the cap is passed."""
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded(f"tool-call budget exceeded ({self.tool_calls} > {self.max_tool_calls})")

    def charge_model_call(self) -> None:
        """Count one model call; raise ``BudgetExceeded`` once the cap is passed."""
        self.model_calls += 1
        if self.model_calls > self.max_model_calls:
            raise BudgetExceeded(f"model-call budget exceeded ({self.model_calls} > {self.max_model_calls})")

    def charge_files(self, count: int) -> None:
        """Add ``count`` to the files-read counter; raise ``BudgetExceeded`` once the cap is passed."""
        self.files_read += count
        if self.files_read > self.max_files:
            raise BudgetExceeded(f"file-read budget exceeded ({self.files_read} > {self.max_files})")

    def remaining_tool_calls(self) -> int:
        """Tool calls left before the cap (never negative)."""
        return max(0, self.max_tool_calls - self.tool_calls)
