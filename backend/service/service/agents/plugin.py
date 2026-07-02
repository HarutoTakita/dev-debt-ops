"""Run-wide ADK plugin that records events as an ``agent_trace`` (issue 069 Phase 3).

A ``BasePlugin`` registered on the ``Runner`` receives every event across all agents
(coordinator + sub-agents via ``AgentTool``), so it is the single place to capture the Twin
Agent's judgement / tool calls / reflections into ``Job.result_data`` — no dedicated UI is
built; the trace is read back via ``GET /api/v1/jobs/{id}``.
"""

from collections.abc import Iterable

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin

from service.agents.trace import event_to_trace
from service.services.secret_redaction import deidentify


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


class SecretRedactionPlugin(BasePlugin):
    """Mask secrets + PII in every LLM request before it leaves the process (issue 217 / 296).

    Registered on the ``Runner``, so it scrubs the model request for **all** agents (Twin Agent and
    the agentified walkthrough / refactor / quiz pipelines). ``before_model_callback`` sees the full
    ``llm_request.contents`` — the single chokepoint where repo content (file bodies merged from tool
    results, agent-composed text) heads to Gemini — so masking there guarantees no plaintext secret
    is sent. Mutates the request parts in place and returns ``None`` so the call proceeds.
    """

    def __init__(self, name: str = "secret_redaction", allowlist: Iterable[str] = ()) -> None:
        """Initialise with a redaction counter and a known-safe ``allowlist``.

        ``allowlist`` carries identifiers the redaction must never mask (e.g. the repo owner / name /
        ``owner/repo`` / branch the agent analyses); without it detect-secrets' entropy plugins flag
        such slugs and strip the coordinates the agent needs for its tool calls (issue 225).
        """
        super().__init__(name=name)
        self.redacted = 0
        self._allowlist = frozenset(token for token in allowlist if token)

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        """Mask secrets + PII in every text part of the outgoing model request, in place.

        part 単位でマスクする（各パートは after_tool_callback の上限で ~12k に収まり、DLP の ~0.5MB 上限に安全）。
        DLP は ``deidentify`` 内で有効時のみ呼ばれ、失敗時はローカルのルールベース PII にフォールバックする。
        """
        for content in llm_request.contents or []:
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text:
                    masked, count = await deidentify(text, allowlist=self._allowlist)
                    if count:
                        part.text = masked
                        self.redacted += count
        return None
