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
from service.agents.github_mcp import build_github_toolset
from service.agents.plugin import SecretRedactionPlugin, TraceRecorderPlugin
from service.agents.semgrep_mcp import build_semgrep_toolset
from service.agents.serena_mcp import build_serena_toolset
from service.agents.trivy_mcp import build_trivy_toolset
from service.agents.twin import build_twin_loop
from service.services.github_git_client import GitHubGitClient

_APP_NAME = "rosetta-twin"


async def run_twin_agent(
    *,
    client: GitHubGitClient,
    owner: str,
    repo: str,
    branch: str,
    budget: RunBudget,
    repo_dir: str | None = None,
    github_token: str | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Run the Twin Agent over one repository; return ``(agent_trace, recommendations)``.

    Optional MCP toolsets ground the specialists: Serena + Trivy when ``repo_dir`` (a checked-out
    tree) is given, and GitHub when ``github_token`` is given. Any that fail to start are simply
    absent — the agent falls back to the REST-based repo tools (graceful).
    """
    recorder = TraceRecorderPlugin()
    # 探索で読んだ内容のシークレットを LLM 送信前に秘匿（issue 217）。owner/repo/branch は既知の安全な識別子
    # なので allowlist で除外（detect-secrets が owner/repo を誤検知し座標を壊すのを防ぐ・issue 225）。
    redactor = SecretRedactionPlugin(allowlist={owner, repo, f"{owner}/{repo}", branch})
    recommendations: list[dict[str, str]] = []
    serena_toolset = build_serena_toolset(repo_dir) if repo_dir else None
    trivy_toolset = build_trivy_toolset() if repo_dir else None
    github_toolset = build_github_toolset(github_token) if github_token else None
    # Semgrep MCP (in-house, stdio, in-venv) needs no clone — it scans the file contents the agent
    # reads — so it grounds the code specialist on every run (issue 204).
    semgrep_toolset = build_semgrep_toolset()
    toolsets = [t for t in (serena_toolset, github_toolset, trivy_toolset, semgrep_toolset) if t is not None]
    root = build_twin_loop(
        client=client,
        budget=budget,
        recommendations=recommendations,
        serena_toolset=serena_toolset,
        github_toolset=github_toolset,
        trivy_toolset=trivy_toolset,
        semgrep_toolset=semgrep_toolset,
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
    message = Content(
        role="user",
        parts=[Part(text=f"リポジトリ {owner}/{repo} のブランチ {branch} の知識負債・技術負債を分析してください。")],
    )
    try:
        async for _event in runner.run_async(user_id=user_id, session_id=adk_session.id, new_message=message):
            # The TraceRecorderPlugin records each event; we just drive the generator to completion.
            pass
    finally:
        # Always shut down every MCP stdio subprocess, even on error / budget abort.
        for toolset in toolsets:
            with contextlib.suppress(Exception):
                await toolset.close()
    return recorder.trace, recommendations
