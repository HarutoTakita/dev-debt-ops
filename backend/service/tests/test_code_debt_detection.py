"""issue 028: code-debt detection — static analysis thresholds + pipeline persistence.

Pure detectors (complexity / duplication / dead, severity quantization, derive_priority) are
unit-tested without I/O. The pipeline ``process`` is run against the test DB with GitHub and
Gemini mocked, asserting ``code_debts`` upsert, the analysis_run, and at-least-once idempotency.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import code_debt_detection
from service.services import code_analysis, gemini_stack_service
from service.services.github_git_client import CommitInfo, FileContent, TreeItem
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeDebt, Job
from shared.pipelines.context import PipelineContext
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest
from shared.schemas.stack_analysis import GitHubRef

# --- pure detectors -------------------------------------------------------


class TestQuantizeSeverity:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0.9, "critical"),
            (0.75, "critical"),
            (0.6, "high"),
            (0.5, "high"),
            (0.3, "medium"),
            (0.25, "medium"),
            (0.1, "low"),
            (0.0, "low"),
        ],
    )
    def test_thresholds(self, score: float, expected: str) -> None:
        assert code_analysis.quantize_severity(score) == expected


class TestVendoredExclusion:
    @pytest.mark.parametrize(
        "path",
        [
            "frontend/node_modules/react/index.js",
            "backend/.venv/lib/python3.13/site-packages/foo.py",
            "frontend/build/app.js",
            "frontend/.svelte-kit/generated/root.svelte",
            "vendor/github.com/x/y.go",
            "service/__pycache__/x.py",
            "dist/bundle.js",
            "lambda_package/urllib3/connection.py",  # デプロイバンドル名 + 同梱の installed module
            "lambda_package/handler.py",  # バンドルディレクトリ直下
            "build_artifacts/botocore/client.py",  # 任意名ディレクトリ配下の第三者パッケージ
            "src/urllib3/util/retry.py",  # 任意位置の installed module（パッケージ名で検出）
            "deploy/requests-2.31.0.dist-info/RECORD",  # pip メタデータ
            "x/foo.egg-info/PKG-INFO",
        ],
    )
    def test_vendored_paths_excluded(self, path: str) -> None:
        assert code_analysis.is_vendored_path(path) is True
        assert code_analysis.is_source_file(path) is False

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/src/lib/app.ts",
            "backend/api/app/main.py",
            "packages/core/index.ts",  # monorepo の自前ソース。vendored ではない
            "src/components/button.tsx",
        ],
    )
    def test_authored_source_kept(self, path: str) -> None:
        assert code_analysis.is_vendored_path(path) is False
        assert code_analysis.is_source_file(path) is True


class TestDerivePriority:
    def test_p0_both_axes_high(self) -> None:
        assert code_analysis.derive_priority(0.7, 0.2) == "P0"  # know = 0.8

    def test_p1_single_axis_high(self) -> None:
        assert code_analysis.derive_priority(0.7, 0.9) == "P1"  # code high, know low
        assert code_analysis.derive_priority(0.1, 0.2) == "P1"  # know high, code low

    def test_p2_single_axis_medium(self) -> None:
        assert code_analysis.derive_priority(0.4, 0.95) == "P2"
        assert code_analysis.derive_priority(0.1, 0.6) == "P2"  # know = 0.4

    def test_p3_both_low(self) -> None:
        assert code_analysis.derive_priority(0.1, 0.95) == "P3"


class TestDetectors:
    def test_complexity_flagged(self) -> None:
        content = "def f(x):\n" + "\n".join(f"    if x == {i} and x or x: pass" for i in range(8))
        cc = code_analysis.cyclomatic_complexity(content, "python")
        assert cc >= code_analysis._COMPLEXITY_MIN
        assert 0.0 <= code_analysis.complexity_score(cc) <= 1.0

    def test_dead_file_detection(self) -> None:
        files = {
            "app/main.py": "from app import util\n",  # entrypoint, references util
            "app/util.py": "x = 1\n",
            "app/orphan.py": "y = 2\n",  # nothing imports it, not an entrypoint
        }
        dead = code_analysis.find_dead_files(files)
        assert "app/orphan.py" in dead
        assert "app/util.py" not in dead  # referenced
        assert "app/main.py" not in dead  # entrypoint


class TestAgentEnrichment:
    """issue 271: the Base Analysis Agent's rationale enriches archaeology_notes (numbers unchanged)."""

    def test_agent_notes_by_file_collapses_rationales(self) -> None:
        base = [
            {"file_path": "a.py", "rationale": "属人化"},
            {"file_path": "a.py", "rationale": "未レビュー"},
            {"file_path": "b.py", "rationale": ""},  # empty rationale dropped
            {"no_path": 1},  # malformed dropped
        ]
        notes = code_debt_detection._agent_notes_by_file(base)
        assert notes == {"a.py": "属人化 / 未レビュー"}
        assert code_debt_detection._agent_notes_by_file(None) == {}

    def test_enrich_findings_appends_only_to_flagged_files(self) -> None:
        findings = [
            code_debt_detection.Finding(
                file_path="a.py",
                type="complexity",
                score=0.8,
                archaeology_notes="det-a",
                code_snippet="",
                estimated_repay_hours=1.0,
            ),
            code_debt_detection.Finding(
                file_path="c.py",
                type="dead",
                score=0.5,
                archaeology_notes="det-c",
                code_snippet="",
                estimated_repay_hours=1.0,
            ),
        ]
        code_debt_detection._enrich_findings(findings, {"a.py": "属人化"})
        assert "det-a" in findings[0].archaeology_notes
        assert "【エージェント所見】属人化" in findings[0].archaeology_notes
        assert findings[0].score == 0.8  # numbers unchanged
        assert findings[1].archaeology_notes == "det-c"  # no agent note for c.py → unchanged


# --- pipeline -------------------------------------------------------------

_MAIN = (
    "def run(x):\n"
    + "\n".join(f"    if x == {i} and x or x:\n        x = {i}" for i in range(10))
    + "\nfrom app import util\n"
)
_FILES = {
    "app/main.py": _MAIN,  # high complexity + references util
    "app/util.py": "VALUE = 1\n",  # simple, referenced
    "app/orphan.py": "UNUSED = 2\n",  # dead
}


class _FakeClient:
    def __init__(self, files: dict[str, str]) -> None:
        self._files = files
        self.closed = False

    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        return [TreeItem(path=p, type="blob", size=len(c)) for p, c in self._files.items()]

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
        return FileContent(path=path, content=self._files[path], sha="sha", size=len(self._files[path]))

    async def list_commits(self, owner: str, repo: str, **kwargs: object) -> list[CommitInfo]:
        return [CommitInfo("abc123", "alice", "a@x.com", 1, "2026-01-01T00:00:00Z", "msg")]

    async def aclose(self) -> None:
        self.closed = True


def _patch(monkeypatch: pytest.MonkeyPatch, files: dict[str, str], ai_probs: dict[str, float]) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_ai(file_map: dict[str, str]) -> dict[str, float]:
        return ai_probs

    async def _no_semgrep(file_map: dict[str, str]) -> list:
        # 既定では Semgrep をオフにして決定的に検証する（実バイナリ実行を避ける）。
        return []

    monkeypatch.setattr(code_debt_detection, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(code_debt_detection, "GitHubGitClient", lambda access_token: _FakeClient(files))
    monkeypatch.setattr(gemini_stack_service, "estimate_ai_generation", _fake_ai)
    monkeypatch.setattr(code_debt_detection.semgrep_scan, "scan_files", _no_semgrep)


async def _seed_job(session_maker: async_sessionmaker, job_id: str) -> None:
    """Create the Job row that run_task would create, so analysis_runs.job_id FK is satisfied."""
    async with session_maker() as session:
        session.add(
            Job(id=uuid.UUID(job_id), job_type=JobType.CODE_DEBT_DETECTION, status=JobStatus.PROCESSING, payload={})
        )
        await session.commit()


def _request() -> CodeDebtDetectionRequest:
    return CodeDebtDetectionRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.CODE_DEBT_DETECTION,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        requested_by="user",
        project_id=str(uuid.uuid4()),
    )


async def test_process_detects_and_persists(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch, _FILES, {"app/main.py": 0.9})
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert result.detected >= 2
    assert result.commit_sha == "abc123"
    assert result.by_type.get("complexity") == 1
    assert result.by_type.get("dead") == 1

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        assert run.kind == JobType.CODE_DEBT_DETECTION.value
        assert run.status == JobStatus.COMPLETED

        debts = (await session.execute(select(CodeDebt).where(CodeDebt.run_id == run.id))).scalars().all()
        by_path_type = {(d.file_path, d.type): d for d in debts}
        complexity = by_path_type[("app/main.py", "complexity")]
        cc = complexity.metrics["cyclomatic_complexity"]
        assert complexity.severity == code_analysis.quantize_severity(code_analysis.complexity_score(cc))
        assert complexity.ai_generation_prob == 0.9
        assert complexity.knowledge_coverage == 0.0  # provisional until 029
        assert ("app/orphan.py", "dead") in by_path_type


async def test_ai_estimate_failure_is_graceful(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """A Gemini failure (e.g. 429 RESOURCE_EXHAUSTED — a non-ValueError APIError) during the optional
    AI-generation estimate must NOT fail code-debt detection; findings persist with prob 0.0."""
    _patch(monkeypatch, _FILES, {})

    async def _raise_429(file_map: dict[str, str]) -> dict[str, float]:
        raise RuntimeError("429 RESOURCE_EXHAUSTED")  # stands in for genai_errors.APIError (not ValueError)

    monkeypatch.setattr(gemini_stack_service, "estimate_ai_generation", _raise_429)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()

    assert result.detected >= 2  # deterministic static-analysis findings are still persisted
    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        assert run.status == JobStatus.COMPLETED
        debts = (await session.execute(select(CodeDebt).where(CodeDebt.run_id == run.id))).scalars().all()
        assert debts
        assert all(d.ai_generation_prob == 0.0 for d in debts)


async def test_semgrep_findings_persisted(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    """Semgrep aggregates are upserted as security/smell code_debts alongside the heuristics (issue 204)."""
    from service.services.semgrep_scan import SemgrepAggregate

    _patch(monkeypatch, _FILES, {})

    async def _fake_scan(files: dict[str, str]) -> list[SemgrepAggregate]:
        return [
            SemgrepAggregate(
                file_path="app/main.py",
                debt_type="security",
                score=0.8,
                notes="Semgrep（セキュリティ）1 件: shell=True",
                metrics={"semgrep_count": 1, "max_severity": "ERROR", "rule_ids": ["r1"], "lines": [3]},
            ),
            SemgrepAggregate(
                file_path="app/util.py", debt_type="smell", score=0.5, notes="Semgrep（コードスメル）2 件", metrics={}
            ),
        ]

    monkeypatch.setattr(code_debt_detection.semgrep_scan, "scan_files", _fake_scan)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()

    assert result.by_type.get("security") == 1
    assert result.by_type.get("smell") == 1

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        debts = {
            (d.file_path, d.type): d
            for d in (await session.execute(select(CodeDebt).where(CodeDebt.run_id == run.id))).scalars().all()
        }
        sec = debts[("app/main.py", "security")]
        assert sec.severity == code_analysis.quantize_severity(0.8)  # critical
        assert sec.metrics["rule_ids"] == ["r1"]


async def test_process_is_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch, _FILES, {})
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()

    # Redelivery reuses the run (keyed by job_id) and upserts — no duplicate rows or runs.
    async with session_maker() as session:
        runs = (
            await session.execute(
                select(func.count()).select_from(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        assert runs == 1
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        first = (
            await session.execute(select(func.count()).select_from(CodeDebt).where(CodeDebt.run_id == run.id))
        ).scalar_one()
        assert first >= 2


async def test_rerun_removes_stale_debts(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    """A finding that disappears on re-run must be deleted, not left stale (issue-042)."""
    request = _request()
    await _seed_job(session_maker, request.job_id)

    # First pass: orphan.py is present → produces a "dead" finding.
    _patch(monkeypatch, _FILES, {})
    async with session_maker() as session:
        await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()

    # Second pass (same job → same run): orphan.py is gone, so its "dead" debt must be removed.
    _patch(monkeypatch, {"app/main.py": _MAIN, "app/util.py": "VALUE = 1\n"}, {})
    async with session_maker() as session:
        await code_debt_detection.process(request, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        debts = (await session.execute(select(CodeDebt).where(CodeDebt.run_id == run.id))).scalars().all()
        keys = {(d.file_path, d.type) for d in debts}
        assert ("app/orphan.py", "dead") not in keys  # stale finding deleted
        assert ("app/main.py", "complexity") in keys  # surviving finding kept
