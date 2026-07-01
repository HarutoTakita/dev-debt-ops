"""Twin Agent graph construction (issue 069 Phases 1–2).

Builds the ADK agent graph that makes the analysis *agentic*. The *orchestration* is a
**rule-based pipeline** (deterministic), while the *judgement* inside each stage is the LLM's:

- a ``SequentialAgent`` runs three stages in a fixed order — knowledge-debt specialist →
  code-debt specialist → remediation strategist — so every stage (and thus every scoped MCP)
  is exercised on every run, instead of relying on a coordinator LLM to remember to call them;
- the two specialist ``LlmAgent`` s autonomously explore the repo with ``build_repo_tools`` +
  their stage-scoped MCP and write findings to session state via ``output_key``;
- the remediation strategist runs last and sees both specialists' findings in the shared session,
  recording the repayment strategy (quiz / learning / repayment_pr) per finding.

The deterministic metrics stay in tools; the *judgement* (which file is riskiest, what to
conclude) is the agents'. Nothing here calls the network — construction is pure.
"""

from typing import Any

from google.adk.agents import LlmAgent, SequentialAgent  # ty: ignore[deprecated]
from google.adk.tools.mcp_tool import McpToolset

from service.agents.budget import RunBudget
from service.agents.hooks import make_after_tool_callback, make_before_model_callback, make_before_tool_callback
from service.agents.model import build_agent_model
from service.agents.remediation import build_remediation_agent
from service.agents.tools import build_repo_tools
from service.services.github_git_client import GitHubGitClient

_KNOWLEDGE_INSTRUCTION = """\
あなたはリポジトリの「知識負債（理解ギャップ）」を調べる専門エージェントです。次の手順で調べてください。
1. list_repo_source_files で対象を把握する。
2. コード構造の把握には【必ず】Serena ツール（まず get_symbols_overview、続いて find_symbol /
   find_referencing_symbols）をシンボル単位で使い、参照関係を辿って全文読みを最小化する
   （補助的に必要なときだけ read_file）。全ファイルを機械的に読まず、リスクの高いものに絞って深掘りする。
3. 理解が属人化・陳腐化していそうな箇所を特定する。
最後に、どの機能/ファイルの理解が危ういかと、その根拠を日本語で簡潔に要約してください。
"""

_CODE_INSTRUCTION = """\
あなたはリポジトリの「技術負債（コード品質・セキュリティ）」を調べる専門エージェントです。次の手順で、
閾値で機械的に拾うのではなく複数シグナルを突き合わせて優先度を判断してください。
1. list_repo_source_files で対象を把握する。
2. コード構造の把握には【必ず】Serena ツール（get_symbols_overview / find_symbol /
   find_referencing_symbols / find_implementations）をシンボル単位で使って効率的に調べる
   （補助的に必要なときだけ read_file）。
3. assess_code_debt で複雑度などの決定的シグナルを確認する。
最後に、どのコードが危ういかと、その根拠を日本語で簡潔に要約してください。
"""

# Mandatory grounding hints appended to a specialist's instruction. Each MCP is scoped to the stage
# where it fits — GitHub(プロセス/履歴) → knowledge debt, Trivy(SCA/secret/misconfig) → code debt —
# and its use is REQUIRED (not "if available") so every MCP is actually exercised each run.
_GITHUB_KNOWLEDGE_HINT = """\

さらに、知識負債の根拠付けとして【必ず】GitHub ツールを使うこと: list_pull_requests /
pull_request_read（レビュー有無・変更ファイル）/ list_commits で、未レビューのまま入った変更や
特定著者に偏った（属人化した）箇所を確認し、所見の根拠に必ず含めてください。
"""
_TRIVY_HINT = """\

さらに、技術負債（セキュリティ）の根拠付けとして【必ず】一度 Trivy の scan_filesystem を次の引数
すべてを指定して呼び出すこと（いずれも必須。省略するとサーバが "targetType is required" で失敗します）:
- target="{repo_dir}"（"." ではなく絶対パスを渡すこと）
- targetType="filesystem"
- scanType=["vuln", "secret", "misconfig"]
- outputFormat="json"
結果から脆弱な依存(SCA)・漏洩した secret・設定ミス(misconfig)を確認し、所見の根拠に必ず含めてください。
"""
_SEMGREP_HINT = """\

さらに、技術負債（コード品質・脆弱性）の根拠付けとして【必ず】scan_code（Semgrep MCP）に、読んだ
ファイルを {"filename": <repo相対パス>, "content": <ファイル内容>} の配列で渡して実静的解析を実行すること。
返る security（セキュリティ/正確性）・smell（保守性）の所見を複雑度などの決定的シグナルと突き合わせ、
所見の根拠に必ず含めてください。
"""
_CGC_HINT = """\

さらに、全体像の把握には【必ず】CodeGraphContext のツールを使うこと: analyze_code_relationships に
repo_path="{repo_dir}" を渡し、module_deps（モジュール依存）/ find_all_callers・call_chain（呼び出し連鎖・
影響範囲＝blast radius）/ dead_code を確認する。全文を闇雲に読まず、まずグラフで「どこを深掘りすべきか・変更の
波及範囲はどこか」の当たりを付け、その上で Serena でシンボルを精読すること。所見の根拠にグラフの知見を含めてください。
"""


def _build_specialist(*, name: str, instruction: str, tools: list[Any], budget: RunBudget, output_key: str) -> LlmAgent:
    """Build one specialist ``LlmAgent`` wired with repo tools + budget callbacks."""
    return LlmAgent(
        model=build_agent_model(),
        name=name,
        instruction=instruction,
        tools=list(tools),
        output_key=output_key,
        before_tool_callback=make_before_tool_callback(budget),
        before_model_callback=make_before_model_callback(budget),
        # 大きなツール結果（Trivy/GitHub/CGC/Serena/Semgrep）を切り詰め、多ターンで履歴が肥大して毎回の
        # リクエストが膨らむ（コスト増・502/タイムアウト誘発）のを防ぐ（issue 260 フォローアップ）。
        after_tool_callback=make_after_tool_callback(),
    )


def build_twin_agent(
    *,
    client: GitHubGitClient,
    budget: RunBudget,
    recommendations: list[dict[str, str]],
    serena_toolset: McpToolset | None = None,
    github_toolset: McpToolset | None = None,
    trivy_toolset: McpToolset | None = None,
    semgrep_toolset: McpToolset | None = None,
    code_graph_toolset: McpToolset | None = None,
    repo_dir: str | None = None,
) -> SequentialAgent:  # ty: ignore[deprecated]
    """Build the rule-based Twin Agent pipeline (``SequentialAgent``: knowledge → code → remediation).

    The orchestration is deterministic — all three stages always run, so every stage-scoped MCP is
    exercised every run (no reliance on a coordinator LLM to remember to call each). Each MCP is
    scoped to the stage where it fits and made a required step of that specialist: Serena (LSP,
    structure) → BOTH specialists; GitHub (PR/review/author history) → knowledge specialist only;
    Trivy (SCA/secret/misconfig over the checked-out ``repo_dir``) → code specialist only. The
    remediation strategist runs last and sees both specialists' findings via the shared session.
    """
    repo_tools = build_repo_tools(client, budget)

    # Serena → both; GitHub → knowledge only; Trivy → code only.
    knowledge_tools: list[Any] = list(repo_tools)
    code_tools: list[Any] = list(repo_tools)
    if serena_toolset is not None:
        knowledge_tools.append(serena_toolset)
        code_tools.append(serena_toolset)

    knowledge_instruction = _KNOWLEDGE_INSTRUCTION
    if github_toolset is not None:
        knowledge_tools.append(github_toolset)
        knowledge_instruction += _GITHUB_KNOWLEDGE_HINT

    code_instruction = _CODE_INSTRUCTION
    if trivy_toolset is not None:
        code_tools.append(trivy_toolset)
        code_instruction += _TRIVY_HINT.format(repo_dir=repo_dir or ".")
    if semgrep_toolset is not None:
        code_tools.append(semgrep_toolset)
        code_instruction += _SEMGREP_HINT
    # CodeGraphContext (マクロ) → BOTH specialists（アーキ/結合は知識負債、影響範囲/dead code は技術負債）。
    if code_graph_toolset is not None:
        knowledge_tools.append(code_graph_toolset)
        code_tools.append(code_graph_toolset)
        cgc_hint = _CGC_HINT.format(repo_dir=repo_dir or ".")
        knowledge_instruction += cgc_hint
        code_instruction += cgc_hint

    knowledge_agent = _build_specialist(
        name="knowledge_debt_agent",
        instruction=knowledge_instruction,
        tools=knowledge_tools,
        budget=budget,
        output_key="knowledge_findings",
    )
    code_agent = _build_specialist(
        name="code_debt_agent",
        instruction=code_instruction,
        tools=code_tools,
        budget=budget,
        output_key="code_findings",
    )
    remediation_agent = build_remediation_agent(recommendations=recommendations, budget=budget)
    # Rule-based pipeline: the three stages always run in order (no coordinator LLM deciding).
    return SequentialAgent(  # ty: ignore[deprecated]
        name="twin_pipeline",
        sub_agents=[knowledge_agent, code_agent, remediation_agent],
    )


def build_twin_loop(
    *,
    client: GitHubGitClient,
    budget: RunBudget,
    recommendations: list[dict[str, str]],
    serena_toolset: McpToolset | None = None,
    github_toolset: McpToolset | None = None,
    trivy_toolset: McpToolset | None = None,
    semgrep_toolset: McpToolset | None = None,
    code_graph_toolset: McpToolset | None = None,
    repo_dir: str | None = None,
) -> SequentialAgent:  # ty: ignore[deprecated]
    """Return the rule-based Twin Agent pipeline (kept as the entrypoint name used by the runner).

    Previously a ``LoopAgent`` wrapped a coordinator for adaptive deepening; replaced by a
    deterministic ``SequentialAgent`` so both specialists (and their scoped MCPs) always run.
    """
    return build_twin_agent(
        client=client,
        budget=budget,
        recommendations=recommendations,
        serena_toolset=serena_toolset,
        github_toolset=github_toolset,
        trivy_toolset=trivy_toolset,
        semgrep_toolset=semgrep_toolset,
        code_graph_toolset=code_graph_toolset,
        repo_dir=repo_dir,
    )
