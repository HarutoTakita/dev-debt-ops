"""Agentic code-walkthrough generation (issue 217 PR2).

Turns the single-file "explain this code" walkthrough into an ADK ``LlmAgent`` instead of a single
direct Gemini call: the agent reads the numbered file (passed in the prompt) and, where it deepens
the explanation, follows referenced symbols / definitions across the repo via the Serena (LSP) MCP
toolset — then commits the result by calling ``save_walkthrough`` (the "exploration tools + confirm
tool" pattern, since ADK can't combine ``output_schema`` with ``tools``).

This builds only the agent graph (pure construction). ``services.code_walkthrough`` clones the repo,
starts Serena, drives it via ``run_single_agent``, and falls back to the direct path on any failure.
"""

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset

from service.agents.budget import RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model

_INSTRUCTION = """\
あなたはファイル「{path}」を学習者に1行ずつ読み解かせるメンターエージェントです。
ユーザーメッセージにそのファイルの全文（行番号つき）が含まれます。

手順:
1. ファイル全体を読み、「読む順」（上から下）の意味のまとまり（関数・ブロック・重要な数行）に区切る。
2. 各区切りの解説を深めるため、必要に応じて Serena ツール（get_symbols_overview / find_symbol /
   find_referencing_symbols / find_declaration）でそのコードが参照するシンボルの定義・参照を辿る。
   盲目的に全ファイルを読まず、解説の質を上げる箇所だけを辿ること。
3. 各区切りの解説（日本語2-3文: 何をしているか / なぜ重要か / 注目点）を作る。

最後に【必ず一度だけ】save_walkthrough を呼び、steps 配列を渡して完了すること。各要素:
- start_line: 開始行（1始まり・左の行番号に厳密一致）
- end_line: 終了行（1始まり）
- start_text: start_line の行の中身を「N: 」プレフィックスを除いて一字一句コピー（照合用）
- title: その区切りの短い見出し
- explanation: 日本語2-3文の解説
区切りは読む順に並べ、最大 {max_steps} 件。
"""


def build_walkthrough_agent(
    *,
    path: str,
    budget: RunBudget,
    captured: list[dict[str, Any]],
    serena_toolset: McpToolset | None = None,
    max_steps: int = 12,
) -> LlmAgent:
    """Build the walkthrough ``LlmAgent``; its ``save_walkthrough`` appends steps to ``captured``.

    ``captured`` is the out-parameter the caller reads after the run (the structured result, since
    the agent also needs tools and so can't use ``output_schema``). Serena is wired when a checked-out
    ``repo_dir`` produced a toolset; without it the agent still works from the numbered prompt alone.
    """

    def save_walkthrough(steps: list[dict[str, Any]]) -> str:
        """Persist the finished walkthrough steps (call exactly once when done).

        Args:
            steps: Ordered list of ``{start_line, end_line, start_text, title, explanation}`` items.

        Returns:
            A confirmation string with the number of steps captured.
        """
        captured.clear()
        captured.extend(step for step in steps if isinstance(step, dict))
        return f"saved {len(captured)} walkthrough steps"

    tools: list[Any] = [save_walkthrough]
    if serena_toolset is not None:
        tools.append(serena_toolset)

    return LlmAgent(
        model=build_agent_model(),
        name="code_walkthrough_agent",
        instruction=_INSTRUCTION.format(path=path, max_steps=max_steps),
        tools=tools,
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
    )
