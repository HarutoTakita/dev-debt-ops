"""Agentic quiz authoring (issue 217 PR3).

Turns quiz generation into an ADK ``LlmAgent`` instead of a single direct Gemini call: the agent
reads the target file (or a feature's representative files) and follows dependencies / referenced
symbols across the repo via the Serena (LSP) MCP toolset to write deeper comprehension questions,
then commits them by calling ``save_quiz`` (the "exploration tools + confirm tool" pattern, since
ADK can't combine ``output_schema`` with ``tools``).

Pure construction only. ``services.quiz_authoring`` clones the repo, starts Serena, drives the agent
via ``run_single_agent``, and falls back to the direct path on any failure / empty result.
"""

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset

from service.agents.budget import RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model

_INSTRUCTION = """\
あなたは対象「{label}」の理解度を測る確認クイズを作る専門エージェントです。
ユーザーメッセージに対象コード（1ファイル、または機能の代表ファイル群）があります。

手順:
1. コードを読み、理解の要点（責務・分岐・データの流れ・落とし穴）を把握する。
2. 必要に応じて Serena ツール（get_symbols_overview / find_symbol / find_referencing_symbols /
   find_declaration）で依存・参照を辿り、単一ファイルで完結しない理解も問えるようにする。
3. 難易度 L1〜L5 の設問を作る（各設問は客観・自動採点可能なもののみ）。

最後に【必ず一度だけ】save_quiz を呼んで完了すること。questions / answer_key のスキーマ:
- questions[]: {{"id": "q1", "kind": "multiple_choice|multiple_select",
  "prompt": "（日本語の設問文）",
  "code_snippet": {{"language": "<言語>", "path": "<引用元パス>",
    "content": "<対象コードから該当箇所を数行そのままコピー（最大25行・プレースホルダ禁止）>"}},
  "choices": [{{"id": "a", "label": "（日本語の選択肢）"}}], "difficulty": "L1|L2|L3|L4|L5"}}
- answer_key: {{"q1": {{"answer": "正解の choice id（複数可）", "rubric": "採点基準"}}}}

重要: 設問文・選択肢は必ず日本語。kind は multiple_choice（正解1つ）か multiple_select（正解1つ以上）
のみで、自由記述は不可。各設問に必ず choices（3〜5個）と code_snippet を付けること。
"""


def build_quiz_agent(
    *,
    label: str,
    budget: RunBudget,
    captured: dict[str, Any],
    serena_toolset: McpToolset | None = None,
) -> LlmAgent:
    """Build the quiz ``LlmAgent``; its ``save_quiz`` writes ``{questions, answer_key}`` into ``captured``.

    ``captured`` is the out-parameter the caller reads after the run. Serena is wired when a
    checked-out ``repo_dir`` produced a toolset; without it the agent still authors from the code in
    the prompt alone.
    """

    def save_quiz(questions: list[dict[str, Any]], answer_key: dict[str, Any]) -> str:
        """Persist the finished quiz (call exactly once when done).

        Args:
            questions: List of question objects (multiple_choice / multiple_select with choices).
            answer_key: Mapping of question id to ``{answer, rubric}``.

        Returns:
            A confirmation string with the number of questions captured.
        """
        cleaned = [q for q in questions if isinstance(q, dict)]
        captured.clear()
        captured.update(questions=cleaned, answer_key=answer_key if isinstance(answer_key, dict) else {})
        return f"saved {len(cleaned)} quiz questions"

    tools: list[Any] = [save_quiz]
    if serena_toolset is not None:
        tools.append(serena_toolset)

    return LlmAgent(
        model=build_agent_model(),
        name="quiz_authoring_agent",
        instruction=_INSTRUCTION.format(label=label),
        tools=tools,
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
    )
