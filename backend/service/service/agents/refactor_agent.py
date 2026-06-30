"""Agentic repayment-refactor proposal (issue 217 PR3).

Turns the "propose a refactor for this code debt" step into an ADK ``LlmAgent`` instead of a single
direct Gemini call: the agent reads the target file and follows referenced symbols / callers across
the repo via the Serena (LSP) MCP toolset to keep the edit safe, then commits the proposal by calling
``save_refactor`` (the "exploration tools + confirm tool" pattern, since ADK can't combine
``output_schema`` with ``tools``).

Pure construction only. ``services.repayment_refactor`` clones the repo, starts Serena, drives the
agent via ``run_single_agent``, applies the plausibility guard, and falls back to the direct path.
The PR write (branch/commit/PR) stays in the pipeline — only the *proposal* is agentified.
"""

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset

from service.agents.budget import RunBudget
from service.agents.hooks import make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model

_INSTRUCTION = """\
あなたはコード負債を返済するリファクタリング案を作る専門エージェントです。
対象ファイルは「{path}」。負債の根拠（考古学ノート）は次の通り:
{notes}

ユーザーメッセージに対象ファイルの現在の全文があります。次の手順で進めてください。
1. ファイルを読み、負債の核心（重複・複雑度・dead code 等）を特定する。
2. 変更の安全性を確かめるため、必要に応じて Serena ツール（find_symbol /
   find_referencing_symbols / find_declaration / get_symbols_overview）でこのコードの
   呼び出し元・参照・定義を辿り、影響範囲を把握する（公開シグネチャを壊さない）。
3. ファイル全体を置き換える**新しい内容**を作る。挙動を保ちつつ負債を減らす、限定的で
   レビュー可能な変更にすること（空ファイルや無関係な全面書き換えは禁止）。

最後に【必ず一度だけ】save_refactor を呼んで完了すること:
- new_content: リファクタ後のファイル全文
- pr_title: 簡潔な PR タイトル
- pr_body: 変更内容と根拠の説明（日本語）
"""


def build_refactor_agent(
    *,
    path: str,
    notes: str,
    budget: RunBudget,
    captured: dict[str, Any],
    serena_toolset: McpToolset | None = None,
) -> LlmAgent:
    """Build the refactor ``LlmAgent``; its ``save_refactor`` writes the proposal into ``captured``.

    ``captured`` is the out-parameter the caller reads after the run (``{new_content, pr_title,
    pr_body}``). Serena is wired when a checked-out ``repo_dir`` produced a toolset; without it the
    agent still proposes from the file content in the prompt alone.
    """

    def save_refactor(new_content: str, pr_title: str, pr_body: str) -> str:
        """Persist the finished refactor proposal (call exactly once when done).

        Args:
            new_content: The full proposed file content after the refactor.
            pr_title: A concise pull-request title.
            pr_body: Japanese explanation of the change and its rationale.

        Returns:
            A confirmation string.
        """
        captured.clear()
        captured.update(new_content=new_content, pr_title=pr_title, pr_body=pr_body)
        return f"saved refactor ({len(new_content)} chars)"

    tools: list[Any] = [save_refactor]
    if serena_toolset is not None:
        tools.append(serena_toolset)

    return LlmAgent(
        model=build_agent_model(),
        name="repayment_refactor_agent",
        instruction=_INSTRUCTION.format(path=path, notes=notes or "(none)"),
        tools=tools,
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
    )
