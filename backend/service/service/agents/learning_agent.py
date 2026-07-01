"""Agentic learning-plan generation (issue 263).

Turns the two single Gemini calls behind a learning plan into ADK ``LlmAgent`` s (one model call
each): a *code-learning-steps* agent (ordered steps to understand a feature's files) and an
*external-resources* agent (learning links for gap concepts). Both use the "confirm tool" pattern
(``save_*``). No repo clone / MCP needed.

Pure construction only. ``services.learning_authoring`` drives them via ``run_single_agent`` and
falls back to the direct ``gemini_stack_service`` calls on any failure / empty result.
"""

from typing import Any

from google.adk.agents import LlmAgent

from service.agents.budget import RunBudget
from service.agents.hooks import make_after_tool_callback, make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model

_STEPS_INSTRUCTION = """\
あなたは、このリポジトリに参加した開発者へ対象機能のコードを理解させるメンターです。ユーザーメッセージに
機能名・説明・構成ファイル一覧があります。コードを読む順に学習ステップを作り、各ステップで対象ファイルの
「何をするコードか」「理解のために注目すべき点」を日本語で簡潔に説明してください。

最後に【必ず一度だけ】save_learning_steps を呼んで完了すること。steps のスキーマ:
- steps[]: {"source_ref": "<構成ファイル一覧のいずれか>", "title": "<ファイル名や扱う話題>",
  "summary": "（日本語 2-3 文）", "estimated_minutes": 15,
  "priority": "required|recommended|supplementary|hands_on"}
"source_ref" は必ず一覧内のファイルにすること。最大 8 ステップ。
"""

_RESOURCES_INSTRUCTION = """\
あなたは技術学習のメンターです。ユーザーメッセージにギャップ概念/技術用語の一覧があります。各用語について、
一般的な学習リソース（公式ドキュメントや定番ガイド）を提案してください。

最後に【必ず一度だけ】save_resources を呼んで完了すること。resources のスキーマ:
- resources[]: {"name": "<技術/概念名>", "title": "<リソース見出し>", "url": "<URL>",
  "summary": "（日本語 1-2 文）", "estimated_minutes": 20}
"""


def build_learning_steps_agent(*, budget: RunBudget, captured: dict[str, Any]) -> LlmAgent:
    """Build the code-learning-steps agent; ``save_learning_steps`` writes ``captured["steps"]``."""

    def save_learning_steps(steps: list[dict[str, Any]]) -> str:
        """Persist the ordered learning steps (call exactly once when done)."""
        cleaned = [s for s in steps if isinstance(s, dict)]
        captured.clear()
        captured["steps"] = cleaned
        return f"saved {len(cleaned)} learning steps"

    return LlmAgent(
        model=build_agent_model(),
        name="learning_steps_agent",
        instruction=_STEPS_INSTRUCTION,
        tools=[save_learning_steps],
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
        after_tool_callback=make_after_tool_callback(),
    )


def build_external_resources_agent(*, budget: RunBudget, captured: dict[str, Any]) -> LlmAgent:
    """Build the external-resources agent; ``save_resources`` writes ``captured["resources"]``."""

    def save_resources(resources: list[dict[str, Any]]) -> str:
        """Persist the external learning resources (call exactly once when done)."""
        cleaned = [r for r in resources if isinstance(r, dict)]
        captured.clear()
        captured["resources"] = cleaned
        return f"saved {len(cleaned)} resources"

    return LlmAgent(
        model=build_agent_model(),
        name="external_resources_agent",
        instruction=_RESOURCES_INSTRUCTION,
        tools=[save_resources],
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
        after_tool_callback=make_after_tool_callback(),
    )
