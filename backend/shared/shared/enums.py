"""Enums shared across api and service (job lifecycle, pipeline kinds).

`JobStatus` / `ResultStatus` values are intentionally UPPERCASE (see issue 016);
`JobType` values are lowercase snake_case identifiers that map to queue / task path
names via `_` -> `-` (e.g. ``stack_analysis`` -> ``stack-analysis``).
"""

from enum import StrEnum


class JobType(StrEnum):
    """Kind of pipeline a Job runs. Value maps to the queue / task path name.

    命名規約（issue 026 で正式化）: 値は **lowercase snake_case** とし、queue / task path 名へは
    ``_`` -> ``-`` 変換で対応する（例: ``code_debt_detection`` -> task path ``code-debt-detection``）。
    新しい解析パイプラインを足す後続 issue（028 以降）は、ここに **1 値ずつ** 同形で追加する。
    ``analysis_run.kind``（``shared/shared/models/analysis_run.py``）はこの値に揃える。
    """

    ECHO = "echo"  # end-to-end plumbing probe (issue 016)
    PING = "ping"  # minimal health pipeline (issue 016)
    STACK_ANALYSIS = "stack_analysis"  # ADK stack analysis (issue 018)
    CODE_DEBT_DETECTION = "code_debt_detection"  # 重複/dead/複雑度 + AI 生成痕跡検知 (issue 028)
    KC_ANALYSIS = "kc_analysis"  # Knowledge Coverage 算出 (authorship/blame + 依存) (issue 029)
    KNOWLEDGE_DEBT_DETECTION = "knowledge_debt_detection"  # AI生成/著者離脱/未レビュー検知 (issue 030)
    REPAYMENT_PR_GENERATION = "repayment_pr_generation"  # Gemini リファクタ案 + GitHub 返済 PR (issue 033)
    QUIZ_GENERATION = "quiz_generation"  # 低 KC ファイルから L1-L5 クイズ生成 (issue 034)
    QUIZ_GRADING = "quiz_grading"  # クイズ意味採点 + KC 反映フック (issue 034)
    LEARNING_PLAN_GENERATION = "learning_plan_generation"  # チーム資産浮上の学習プラン生成 (issue 035)
    CODE_WALKTHROUGH_GENERATION = "code_walkthrough_generation"  # コード理解の行ごと解説を Gemini で生成
    # 廃止: Twin Agent 自律ループ (issue 036) は削除済み。値は既存 jobs 行のロード互換のためだけに残す。
    CODE_DEBT_LOOP = "code_debt_loop"
    KNOWLEDGE_DEBT_LOOP = "knowledge_debt_loop"
    FEATURE_CLUSTERING = "feature_clustering"  # Gemini でファイル群を機能へクラスタリング (issue 052)


class Granularity(StrEnum):
    """Measurement granularity shared by debt/KC rows, API and frontend (issue 052).

    MVP で実計測・表示するのは ``feature``（052 系列）と既存の ``file``。``folder`` は既存の
    ``file_kc.module``（= ディレクトリ）を射影して導出可能。``class`` / ``function`` は値だけ
    先行定義し、実計測は issue 057（AST 解析）へ送る（API / フロント契約の早期安定化）。
    """

    FEATURE = "feature"
    FOLDER = "folder"
    FILE = "file"
    CLASS = "class"  # 後続（057）
    FUNCTION = "function"  # 後続（057）


class JobStatus(StrEnum):
    """Lifecycle state of a Job row. Values are UPPERCASE (issue 016)."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResultStatus(StrEnum):
    """Terminal status a pipeline reports for its result. Values are UPPERCASE."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
