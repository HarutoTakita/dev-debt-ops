"""Generic single-agent runner (issue 217).

Drives one ADK agent to completion under a ``Runner`` wired with the run-wide plugins every
agentic pipeline wants: ``TraceRecorderPlugin`` (records the ``agent_trace``) and
``SecretRedactionPlugin`` (masks secrets in every model request). Generalises the boilerplate in
``runner.run_twin_agent`` / ``stack_analysis.run_stack_analysis`` so the walkthrough / refactor /
quiz pipelines (PR2/PR3) only build their agent + tools and call this — they all get tracing and
secret redaction for free, and any MCP stdio subprocesses are always shut down.

Tests patch this function (the ADK ``Runner`` is never driven without a live model), mirroring the
stack-analysis approach, so the pipelines stay unit-testable without Vertex AI.
"""

import contextlib
from collections.abc import Sequence

from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.genai.types import Content, Part

from service.agents.plugin import SecretRedactionPlugin, TraceRecorderPlugin

_APP_NAME = "rosetta-agent"


async def run_single_agent(
    *,
    agent: BaseAgent,
    prompt: str,
    user_id: str,
    app_name: str = _APP_NAME,
    toolsets: Sequence[McpToolset] | None = None,
) -> list[str]:
    """Run ``agent`` over one ``prompt`` to completion; return its ``agent_trace``.

    The Runner is registered with a trace recorder and a secret-redaction plugin, so every model
    request is scrubbed of secrets before it leaves the process and every tool call / response /
    final summary is captured. ``toolsets`` (any MCP toolsets the agent uses) are closed in a
    ``finally`` so their stdio subprocesses never leak, even on error or budget abort.
    """
    recorder = TraceRecorderPlugin()
    redactor = SecretRedactionPlugin()  # 探索で読んだ内容のシークレットを LLM 送信前に秘匿（issue 217）
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=agent,
        session_service=session_service,
        plugins=[recorder, redactor],
    )
    adk_session = await session_service.create_session(app_name=app_name, user_id=user_id)
    message = Content(role="user", parts=[Part(text=prompt)])
    try:
        async for _event in runner.run_async(user_id=user_id, session_id=adk_session.id, new_message=message):
            # The TraceRecorderPlugin records each event; we just drive the generator to completion.
            pass
    finally:
        for toolset in toolsets or []:
            with contextlib.suppress(Exception):
                await toolset.close()
    return recorder.trace
