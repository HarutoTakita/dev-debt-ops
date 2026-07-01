"""Run the Base Repository Analysis Agent and collect its trace + output (issue 069 → 266).

Builds the agent graph, drives the ADK ``Runner``, and returns ``(agent_trace, base_analysis)``.
Trace is captured by the ``TraceRecorderPlugin`` registered on the Runner (run-wide event hook), so
sub-agent events are included; secrets are masked by ``SecretRedactionPlugin`` before every model
request.

Tests patch this function (the ADK Runner is never driven without a live model), so the
``agentic_analysis`` pipeline can be exercised without Vertex AI — same approach as stack-analysis.
"""

import contextlib
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from service.agents.base_analysis_tools import build_analysis_agent, build_base_analysis
from service.agents.budget import RunBudget
from service.agents.code_graph_mcp import build_code_graph_toolset
from service.agents.github_mcp import build_github_toolset
from service.agents.plugin import SecretRedactionPlugin, TraceRecorderPlugin
from service.agents.serena_mcp import build_serena_toolset
from service.services.github_git_client import GitHubGitClient
from shared.schemas.base_analysis import BaseAnalysis

_APP_NAME = "rosetta-analysis"


async def run_analysis_agent(
    *,
    client: GitHubGitClient,
    owner: str,
    repo: str,
    branch: str,
    budget: RunBudget,
    repo_dir: str | None = None,
    github_token: str | None = None,
) -> tuple[list[str], BaseAnalysis]:
    """Run the Base Analysis Agent over one repository; return ``(agent_trace, base_analysis)``.

    The agent-first "元データ" producer (issue 266): a two-stage agent explores the repo with the
    *exploration* MCP toolsets (Serena when ``repo_dir`` is given, GitHub when ``github_token`` is
    given, CodeGraphContext when ``repo_dir`` is given) and confirms a qualitative ``BaseAnalysis``
    via ``save_base_analysis``. Deterministic measurement (KC / complexity / semgrep / Trivy) runs as
    its own program blocks afterwards — intentionally NOT attached here. Any toolset that fails to
    start is simply absent (graceful). Tests patch this function (no live model).
    """
    recorder = TraceRecorderPlugin()
    redactor = SecretRedactionPlugin(allowlist={owner, repo, f"{owner}/{repo}", branch})
    captured: dict[str, Any] = {}
    serena_toolset = build_serena_toolset(repo_dir) if repo_dir else None
    github_toolset = build_github_toolset(github_token) if github_token else None
    code_graph_toolset = build_code_graph_toolset() if repo_dir else None
    toolsets = [t for t in (serena_toolset, github_toolset, code_graph_toolset) if t is not None]
    root = build_analysis_agent(
        client=client,
        budget=budget,
        captured=captured,
        serena_toolset=serena_toolset,
        github_toolset=github_toolset,
        code_graph_toolset=code_graph_toolset,
        repo_dir=repo_dir,
    )
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=_APP_NAME,
        agent=root,
        session_service=session_service,
        plugins=[recorder, redactor],
    )
    user_id = f"{owner}_{repo}"
    adk_session = await session_service.create_session(app_name=_APP_NAME, user_id=user_id)
    seed = f"リポジトリ {owner}/{repo} のブランチ {branch} を解析し、後続処理の元データを作成してください。"
    message = Content(role="user", parts=[Part(text=seed)])
    try:
        async for _event in runner.run_async(user_id=user_id, session_id=adk_session.id, new_message=message):
            pass
    finally:
        for toolset in toolsets:
            with contextlib.suppress(Exception):
                await toolset.close()
    return recorder.trace, build_base_analysis(captured)
