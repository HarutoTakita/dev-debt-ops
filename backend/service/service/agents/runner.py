"""Run the Twin Agent and collect its trace (issue 069).

Mirrors ``stack_analysis.run_stack_analysis``: build the agent graph, drive the ADK ``Runner``,
and return the ``agent_trace``. Trace is captured by the ``TraceRecorderPlugin`` registered on
the Runner (run-wide event hook), so sub-agent events delegated via ``AgentTool`` are included.

Tests patch this function (the ADK Runner is never driven without a live model), so the
``agentic_analysis`` pipeline can be exercised without Vertex AI — same approach as stack-analysis.
"""

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from service.agents.budget import RunBudget
from service.agents.plugin import TraceRecorderPlugin
from service.agents.twin import build_twin_loop
from service.services.github_git_client import GitHubGitClient

_APP_NAME = "rosetta-twin"


async def run_twin_agent(
    *, client: GitHubGitClient, owner: str, repo: str, branch: str, budget: RunBudget
) -> list[str]:
    """Run the Twin Agent over one repository and return its ``agent_trace``."""
    recorder = TraceRecorderPlugin()
    root = build_twin_loop(client=client, budget=budget)
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
    async for _event in runner.run_async(user_id=user_id, session_id=adk_session.id, new_message=message):
        # The TraceRecorderPlugin records each event; we just drive the generator to completion.
        pass
    return recorder.trace
