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
