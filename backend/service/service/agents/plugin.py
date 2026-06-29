"""Run-wide ADK plugin that records events as an ``agent_trace`` (issue 069 Phase 3).

A ``BasePlugin`` registered on the ``Runner`` receives every event across all agents
(coordinator + sub-agents via ``AgentTool``), so it is the single place to capture the Twin
Agent's judgement / tool calls / reflections into ``Job.result_data`` — no dedicated UI is
built; the trace is read back via ``GET /api/v1/jobs/{id}``.
"""

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin

from service.agents.trace import event_to_trace


class TraceRecorderPlugin(BasePlugin):
    """Collects ``agent_trace`` lines from every Runner event."""

    def __init__(self, name: str = "trace_recorder") -> None:
        """Initialise with an empty trace buffer."""
        super().__init__(name=name)
        self.trace: list[str] = []

    async def on_event_callback(self, *, invocation_context: InvocationContext, event: Event) -> Event | None:
        """Append the event's trace lines; return ``None`` to leave the event unchanged."""
        self.trace.extend(event_to_trace(event))
        return None
