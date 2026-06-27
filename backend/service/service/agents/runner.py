"""Run the Twin Agent and collect its trace (issue 069).

Mirrors ``stack_analysis.run_stack_analysis``: build the agent graph, drive the ADK ``Runner``,
and return the ``agent_trace``. Trace is captured by the ``TraceRecorderPlugin`` registered on
the Runner (run-wide event hook), so sub-agent events delegated via ``AgentTool`` are included.

Tests patch this function (the ADK Runner is never driven without a live model), so the
``agentic_analysis`` pipeline can be exercised without Vertex AI — same approach as stack-analysis.
"""

import contextlib

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from service.agents.budget import RunBudget
from service.agents.plugin import TraceRecorderPlugin
from service.agents.tools import build_semgrep_toolset
from service.agents.twin import build_twin_loop
from service.services.github_git_client import GitHubGitClient

_APP_NAME = "rosetta-twin"


async def run_twin_agent(
    *, client: GitHubGitClient, owner: str, repo: str, branch: str, budget: RunBudget
) -> tuple[list[str], list[dict[str, str]]]:
    """Run the Twin Agent over one repository; return ``(agent_trace, recommendations)``."""
    recorder = TraceRecorderPlugin()
    recommendations: list[dict[str, str]] = []
    # Semgrep MCP server (in-house, stdio) grounds the code specialist in real static analysis.
    semgrep_toolset = build_semgrep_toolset()
    root = build_twin_loop(
        client=client, budget=budget, recommendations=recommendations, semgrep_toolset=semgrep_toolset
    )
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=_APP_NAME,
        agent=root,
        session_service=session_service,
        plugins=[recorder],
    )
    user_id = f"{owner}_{repo}"
    adk_session = await session_service.create_session(app_name=_APP_NAME, user_id=user_id)
    message = Content(
        role="user",
        parts=[Part(text=f"リポジトリ {owner}/{repo} のブランチ {branch} の知識負債・技術負債を分析してください。")],
    )
    try:
        async for _event in runner.run_async(user_id=user_id, session_id=adk_session.id, new_message=message):
            # The TraceRecorderPlugin records each event; we just drive the generator to completion.
            pass
    finally:
        # Always shut down the Semgrep MCP stdio subprocess, even on error/budget abort.
        with contextlib.suppress(Exception):  # cleanup failure must not mask the run result
            await semgrep_toolset.close()
    return recorder.trace, recommendations
