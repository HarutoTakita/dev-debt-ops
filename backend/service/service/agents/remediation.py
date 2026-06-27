"""Remediation strategist agent + tool (issue 069 Phase 4).

After detection, the Twin Agent decides *how to repay* each finding — quiz (active
understanding measurement), learning (acquire the knowledge), or a repayment PR (fix the
code). That judgement is the agent's; the tool just records the structured recommendation so
the result can carry the agent's chosen strategy (the heavy generation pipelines stay the tool
implementations and are driven by the existing analysis flow).
"""

from collections.abc import Callable
from typing import Any

from google.adk.agents import LlmAgent

from service.agents.budget import RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import vertex_model_name

ACTIONS = frozenset({"quiz", "learning", "repayment_pr"})

_REMEDIATION_INSTRUCTION = """\
あなたは返済戦略を決める専門エージェントです。検知された負債（知識/技術）の所見ごとに、最適な返済手段を
判断し recommend_remediation で 1 件ずつ記録してください。
- quiz: 理解を能動測定したい知識ギャップ
- learning: 学習で習得すべきチーム資産・概念
- repayment_pr: コードを修正すべき技術負債
対象・負債種別・選んだ手段・理由（日本語）を必ず記録すること。
"""


def build_remediation_tools(recommendations: list[dict[str, str]]) -> list[Callable[..., Any]]:
    """Build the remediation tool, appending structured recommendations to ``recommendations``."""

    def recommend_remediation(target: str, debt_kind: str, action: str, rationale: str) -> str:
        """Record a remediation recommendation for one finding.

        Args:
            target: The file or feature the recommendation applies to.
            debt_kind: ``"knowledge"`` or ``"code"``.
            action: ``"quiz"`` (理解測定) / ``"learning"`` (学習) / ``"repayment_pr"`` (コード修正).
            rationale: Why this action fits, in Japanese.

        Returns:
            A short confirmation string.
        """
        normalized = action if action in ACTIONS else "other"
        recommendations.append({"target": target, "debt_kind": debt_kind, "action": normalized, "rationale": rationale})
        return f"recorded {normalized} for {target}"

    return [recommend_remediation]


def build_remediation_agent(*, recommendations: list[dict[str, str]], budget: RunBudget) -> LlmAgent:
    """Build the Remediation Strategist ``LlmAgent`` (records quiz/learning/PR decisions)."""
    return LlmAgent(
        model=vertex_model_name(),
        name="remediation_strategist",
        instruction=_REMEDIATION_INSTRUCTION,
        tools=list(build_remediation_tools(recommendations)),
        output_key="remediation",
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
    )
