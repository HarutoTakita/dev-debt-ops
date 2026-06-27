"""Twin Agent graph construction (issue 069 Phases 1–2).

Builds the ADK agent graph that makes the analysis *agentic*:

- two specialist ``LlmAgent`` s (knowledge-debt / code-debt) that autonomously explore the repo
  with ``build_repo_tools`` and write their findings to session state via ``output_key``;
- a coordinator ``LlmAgent`` with a ``PlanReActPlanner`` that delegates to the specialists via
  ``AgentTool`` and decides when the analysis is sufficient (calling ``exit_loop``);
- a ``LoopAgent`` wrapper that re-runs the coordinator for adaptive deepening, bounded by
  ``max_iterations`` and the run budget (enforced by the before-tool / before-model callbacks).

The deterministic metrics stay in tools; the *judgement* (which feature is riskiest, how deep
to dig, what to conclude) is the agents'. Nothing here calls the network — construction is pure.
"""

from collections.abc import Callable
from typing import Any

from google.adk.agents import LlmAgent, LoopAgent  # ty: ignore[deprecated]
from google.adk.planners import PlanReActPlanner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.exit_loop_tool import exit_loop

from service.agents.budget import RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import vertex_model_name
from service.agents.remediation import build_remediation_agent
from service.agents.tools import build_repo_tools
from service.services.github_git_client import GitHubGitClient

_DEFAULT_MAX_ITERATIONS = 2

_KNOWLEDGE_INSTRUCTION = """\
あなたはリポジトリの「知識負債（理解ギャップ）」を調べる専門エージェントです。
list_repo_source_files で対象を把握し、危ういと判断したファイルだけを read_file で読み、
理解が属人化・陳腐化していそうな箇所を特定してください。全ファイルを機械的に読まず、
リスクの高いものに絞って深掘りすること。最後に、どの機能/ファイルの理解が危ういかと、その根拠を
日本語で簡潔に要約してください。
"""

_CODE_INSTRUCTION = """\
あなたはリポジトリの「技術負債（コード品質）」を調べる専門エージェントです。
list_repo_source_files で対象を把握し、怪しいファイルを read_file で読み、assess_code_debt で
複雑度などの決定的シグナルを確認して、リスクの高いコード負債を特定してください。閾値で機械的に
拾うのではなく、複数シグナルを突き合わせて優先度を判断すること。最後に、どのコードが危ういかと
その根拠を日本語で簡潔に要約してください。
"""

_TWIN_INSTRUCTION = """\
あなたはリポジトリ全体を統括する Twin Agent です。知識負債と技術負債のどちらがどれだけ危ういかを
判断し、knowledge_debt_agent / code_debt_agent ツールに調査を委譲してください。両者の結果を踏まえ、
まだ調べ足りなければ追加で委譲します。検知が十分に進んだら remediation_strategist に委譲し、各所見の
返済手段（quiz/learning/repayment_pr）を記録させてください。十分に把握できたと判断したら exit_loop を
呼んで分析を終了し、最も危険な負債とその根拠・推奨アクションを日本語で簡潔にまとめてください。
"""


def _build_specialist(
    *, name: str, instruction: str, tools: list[Callable[..., Any]], budget: RunBudget, output_key: str
) -> LlmAgent:
    """Build one specialist ``LlmAgent`` wired with repo tools + budget callbacks."""
    return LlmAgent(
        model=vertex_model_name(),
        name=name,
        instruction=instruction,
        tools=list(tools),
        output_key=output_key,
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
    )


def build_twin_agent(*, client: GitHubGitClient, budget: RunBudget, recommendations: list[dict[str, str]]) -> LlmAgent:
    """Build the coordinator ``LlmAgent`` (PlanReActPlanner + AgentTool specialists + exit_loop).

    Delegates detection to the knowledge/code specialists and remediation to the strategist
    (which records its quiz/learning/PR decisions into ``recommendations``).
    """
    repo_tools = build_repo_tools(client, budget)
    knowledge_agent = _build_specialist(
        name="knowledge_debt_agent",
        instruction=_KNOWLEDGE_INSTRUCTION,
        tools=repo_tools,
        budget=budget,
        output_key="knowledge_findings",
    )
    code_agent = _build_specialist(
        name="code_debt_agent",
        instruction=_CODE_INSTRUCTION,
        tools=repo_tools,
        budget=budget,
        output_key="code_findings",
    )
    remediation_agent = build_remediation_agent(recommendations=recommendations, budget=budget)
    coordinator_tools: list[Any] = [
        AgentTool(agent=knowledge_agent),
        AgentTool(agent=code_agent),
        AgentTool(agent=remediation_agent),
        exit_loop,
    ]
    return LlmAgent(
        model=vertex_model_name(),
        name="twin_agent",
        planner=PlanReActPlanner(),
        instruction=_TWIN_INSTRUCTION,
        tools=coordinator_tools,
        before_model_callback=make_before_model_callback(budget),
    )


def build_twin_loop(
    *,
    client: GitHubGitClient,
    budget: RunBudget,
    recommendations: list[dict[str, str]],
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
) -> LoopAgent:  # ty: ignore[deprecated]
    """Wrap the coordinator in a ``LoopAgent`` for adaptive deepening.

    The loop re-runs the coordinator until it calls ``exit_loop`` (escalate) or ``max_iterations``
    is reached — the autonomous "keep investigating the riskiest area until confident or budget"
    behaviour, bounded mechanically by the loop cap and the run budget.

    Note: ``LoopAgent`` is deprecated in adk 2.2.0 (→ Workflow) but still functional; migrating
    to the Workflow API is a follow-up.
    """
    coordinator = build_twin_agent(client=client, budget=budget, recommendations=recommendations)
    return LoopAgent(  # ty: ignore[deprecated]
        name="twin_loop", sub_agents=[coordinator], max_iterations=max_iterations
    )
