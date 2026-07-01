"""Base Repository Analysis Agent — the agent-first "元データ" producer (issue 266).

Agent-first re-architecture: the main repository analysis IS this agent. It runs FIRST and emits one
canonical, *qualitative* ``BaseAnalysis`` (features / key concepts / code & knowledge risk narrative),
which downstream blocks then format/enhance into the screen tables. Deterministic *measurements*
(KC blame, complexity/semgrep, ai-generation) run as their own program blocks — NOT as tools the LLM
calls (a tool call = an extra model turn = latency/cost) — so this agent carries only exploration MCP.

Shape: a two-stage ``SequentialAgent`` (proven more reliable than one monolithic agent — a Sequential
exercises each stage every run instead of hoping one agent remembers to explore *and* save):

1. ``analysis_explorer`` — MCP (Serena / GitHub / CodeGraphContext) + repo tools; explores structure,
   history and hotspots. Writes its findings to session state via ``output_key="exploration"``.
2. ``base_author`` — reads ``{exploration}`` and calls ``save_base_analysis`` ONCE (the confirm-tool
   pattern — ADK can't combine ``output_schema`` with ``tools``), writing into ``captured``.

Construction is pure (no network). ``runner.run_analysis_agent`` drives it via the ADK ``Runner`` and
builds a ``BaseAnalysis`` from ``captured``; an empty/failed run makes downstream fall back to the
deterministic pipelines.
"""

from typing import Any

from google.adk.agents import LlmAgent, SequentialAgent  # ty: ignore[deprecated]
from google.adk.tools.mcp_tool import McpToolset
from pydantic import BaseModel

from service.agents.budget import RunBudget
from service.agents.hooks import make_after_tool_callback, make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model
from service.agents.tools import build_repo_tools
from service.services.github_git_client import GitHubGitClient
from shared.schemas.base_analysis import (
    BaseAnalysis,
    BaseCodeFinding,
    BaseFeature,
    BaseKnowledgeFinding,
)

_EXPLORER_INSTRUCTION = """\
あなたはリポジトリ全体を理解する「解析エージェント」です。後続処理（理解度マップ / コード品質 /
学習プラン / クイズ）の土台となる定性的な元データを作るために、まずリポジトリを調べてください。

手順:
1. list_repo_source_files で対象ファイルを把握する。
2. 構造把握には【必ず】Serena（get_symbols_overview → find_symbol / find_referencing_symbols）を
   シンボル単位で使い、全文読みを最小化する（補助的に必要なときだけ read_file）。
3. GitHub ツール（list_pull_requests / pull_request_read / list_commits）でレビュー有無・著者の偏り
   （属人化）など、理解が危うい箇所の根拠を集める。
4. CodeGraphContext（analyze_code_relationships）で module 依存・呼び出し連鎖・影響範囲・dead code を
   把握し、深掘りすべき箇所の当たりを付ける。

次のことを日本語で簡潔に整理して出力してください（保存はまだしない）:
- 意味的な「機能（feature）」の候補と所属ファイル、各機能の学習上の重要概念（key concepts）。
- コード品質の懸念（複雑・重複・dead・セキュリティ等）が疑われるファイルとその理由。
- 理解が属人化/陳腐化/未レビューで危ういファイルとその理由。
数値（複雑度スコアや理解度など）は算出しなくてよい（後段の決定的処理が計測する）。判断と根拠に集中すること。
"""

_AUTHOR_INSTRUCTION = """\
あなたは解析結果を確定するエージェントです。直前の探索でまとめた所見が以下にあります:

<exploration>
{exploration}
</exploration>

この所見に基づき、【必ず一度だけ】save_base_analysis を呼んで元データを確定してください。各引数のスキーマ:
- features[]: {{"key": "小文字 kebab/snake の安定 slug（英語可）",
  "name": "日本語の分かりやすい機能名（例: 認証、課金、解析パイプライン）", "description": "1〜2 行（日本語）",
  "files": [{{"path": "探索で現れた正確なパス", "confidence": 0.0〜1.0}}],
  "key_concepts": ["学習上の重要概念", ...], "risk_notes": "理解リスクの叙述（任意）"}}
- code_findings[]: {{"file_path": "パス", "type": "complexity|duplicate|dead|security|smell|other",
  "severity": "low|medium|high", "rationale": "根拠（日本語）", "snippet": "任意"}}
- knowledge_findings[]: {{"file_path": "パス", "reason": "ai_generated|author_left|no_review|other",
  "rationale": "根拠（日本語）", "risk_signal": "任意"}}
- stack_terms[]: 技術スタックのヒント語（任意）
- summary: 全体所見の 1〜3 行要約
ルール: パスは探索で実在が確認できたものだけを使う。数値は入れない（判断・分類・根拠のみ）。
機能名（name）と説明（description）は**必ず自然な日本語**にする
（英語のクラス名／ファイル名／"~ API" 等の羅列にしない。key だけは英語 slug 可）。
"""


def build_base_analysis(captured: dict[str, Any]) -> BaseAnalysis:
    """Assemble a ``BaseAnalysis`` from the agent's ``captured`` dict, tolerant to malformed items.

    Each list item is validated individually; unparsable items are dropped rather than failing the
    whole analysis (a bad LLM item must not sink the run — downstream can still use the good ones).
    """

    def _items(key: str, model: type[BaseModel]) -> list:
        out = []
        for raw in captured.get(key, []) or []:
            if not isinstance(raw, dict):
                continue
            try:
                out.append(model.model_validate(raw))
            except Exception:  # skip a single malformed item; keep the rest
                continue
        return out

    summary = captured.get("summary")
    return BaseAnalysis(
        features=_items("features", BaseFeature),
        code_findings=_items("code_findings", BaseCodeFinding),
        knowledge_findings=_items("knowledge_findings", BaseKnowledgeFinding),
        stack_terms=[t for t in (captured.get("stack_terms") or []) if isinstance(t, str)],
        summary=summary if isinstance(summary, str) else "",
    )


def _make_save_base_analysis(captured: dict[str, Any]):
    """Build the ``save_base_analysis`` confirm-tool that records the agent output into ``captured``."""

    def save_base_analysis(
        features: list[dict[str, Any]],
        code_findings: list[dict[str, Any]],
        knowledge_findings: list[dict[str, Any]],
        stack_terms: list[str],
        summary: str,
    ) -> str:
        """Persist the base analysis (call exactly once when done).

        Args:
            features: ``[{key, name, description, files:[{path, confidence}], key_concepts, risk_notes}]``.
            code_findings: ``[{file_path, type, severity, rationale, snippet}]``.
            knowledge_findings: ``[{file_path, reason, rationale, risk_signal}]``.
            stack_terms: Optional tech-stack hint terms.
            summary: A 1–3 line overall summary.

        Returns:
            A confirmation string with the captured counts.
        """
        captured["features"] = [f for f in (features or []) if isinstance(f, dict) and f.get("key")]
        captured["code_findings"] = [c for c in (code_findings or []) if isinstance(c, dict) and c.get("file_path")]
        captured["knowledge_findings"] = [
            k for k in (knowledge_findings or []) if isinstance(k, dict) and k.get("file_path")
        ]
        captured["stack_terms"] = [t for t in (stack_terms or []) if isinstance(t, str)]
        captured["summary"] = summary if isinstance(summary, str) else ""
        return (
            f"saved base analysis: {len(captured['features'])} features, "
            f"{len(captured['code_findings'])} code findings, "
            f"{len(captured['knowledge_findings'])} knowledge findings"
        )

    return save_base_analysis


def build_analysis_agent(
    *,
    client: GitHubGitClient,
    budget: RunBudget,
    captured: dict[str, Any],
    serena_toolset: McpToolset | None = None,
    github_toolset: McpToolset | None = None,
    code_graph_toolset: McpToolset | None = None,
    repo_dir: str | None = None,
) -> SequentialAgent:  # ty: ignore[deprecated]
    """Build the two-stage Base Analysis Agent (explorer → author).

    The explorer gets the repo tools + the exploration MCP toolsets (Serena / GitHub / CGC). The
    author gets only ``save_base_analysis`` and reads the explorer's findings from session state
    (``{exploration}``). Deterministic measurement (KC / complexity / semgrep) is intentionally NOT
    exposed here — those run as their own program blocks after this agent.
    """
    explorer_tools: list[Any] = list(build_repo_tools(client, budget))
    for toolset in (serena_toolset, github_toolset, code_graph_toolset):
        if toolset is not None:
            explorer_tools.append(toolset)

    explorer = LlmAgent(
        model=build_agent_model(),
        name="analysis_explorer",
        instruction=_EXPLORER_INSTRUCTION,
        tools=explorer_tools,
        output_key="exploration",
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
        # 大きなツール結果を切り詰め、多ターンで履歴が肥大しリクエストが膨らむ（コスト増・502/timeout）のを防ぐ。
        after_tool_callback=make_after_tool_callback(),
    )
    author = LlmAgent(
        model=build_agent_model(),
        name="base_author",
        instruction=_AUTHOR_INSTRUCTION,
        tools=[_make_save_base_analysis(captured)],
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
        after_tool_callback=make_after_tool_callback(),
    )
    return SequentialAgent(name="base_analysis_pipeline", sub_agents=[explorer, author])  # ty: ignore[deprecated]
