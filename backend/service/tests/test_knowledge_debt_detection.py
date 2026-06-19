"""issue 030: knowledge-debt detection — reason detection + KC join + idempotency.

Pure detectors are unit-tested. The pipeline ``process`` runs against the test DB with GitHub and
Gemini mocked, asserting one debt per reason (ai_generated / author_left / no_review), the file_kc
join (knowledge_coverage + assigned_developers coverage/certified_via), and at-least-once idempotency.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import knowledge_debt_detection
from service.services import gemini_stack_service, knowledge_analysis
from service.services.github_git_client import CommitInfo, FileContent, ReviewInfo, TreeItem
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, AssignedDeveloper, FileKc, Job, KnowledgeDebt
from shared.pipelines.context import PipelineContext
from shared.schemas.knowledge_debt_detection import KnowledgeDebtDetectionRequest
from shared.schemas.stack_analysis import GitHubRef

_NOW = datetime.now(UTC)
_RECENT = (_NOW - timedelta(days=10)).isoformat()
_OLD = (_NOW - timedelta(days=600)).isoformat()


class TestPureDetectors:
    def test_is_ai_generated(self) -> None:
        assert knowledge_analysis.is_ai_generated(0.5)
        assert not knowledge_analysis.is_ai_generated(0.49)

    def test_is_author_left(self) -> None:
        assert knowledge_analysis.is_author_left(180)
        assert not knowledge_analysis.is_author_left(179)

    def test_is_no_review(self) -> None:
        assert knowledge_analysis.is_no_review([], set())  # direct push
        assert knowledge_analysis.is_no_review([3], set())  # PR not reviewed
        assert not knowledge_analysis.is_no_review([1], {1})  # PR reviewed

    def test_reason_score(self) -> None:
        assert knowledge_analysis.reason_score("ai_generated", ai_prob=0.9, age_days=0) == 0.9
        assert knowledge_analysis.reason_score("no_review", ai_prob=0.0, age_days=0) == 0.6


# --- pipeline -------------------------------------------------------------

_FILES = {"pkg/ai.py": "x = 1\n", "pkg/old.py": "y = 2\n", "pkg/unreviewed.py": "z = 3\n"}
_COMMITS = {
    "pkg/ai.py": CommitInfo("sha_ai", "alice", "a@x.com", 1, _RECENT, "m"),
    "pkg/old.py": CommitInfo("sha_old", "alice", "a@x.com", 1, _OLD, "m"),
    "pkg/unreviewed.py": CommitInfo("sha_un", "alice", "a@x.com", 1, _RECENT, "m"),
}
_PULLS = {"sha_ai": [1], "sha_old": [2], "sha_un": [3]}
_REVIEWS = {
    1: [ReviewInfo("APPROVED", "rev", "t")],
    2: [ReviewInfo("APPROVED", "rev", "t")],
    3: [ReviewInfo("COMMENTED", "rev", "t")],  # not approved → no_review
}


class _FakeClient:
    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        return [TreeItem(path=p, type="blob", size=len(c)) for p, c in _FILES.items()]

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
        return FileContent(path=path, content=_FILES[path], sha="sha", size=len(_FILES[path]))

    async def list_commits(
        self, owner: str, repo: str, *, path: str | None = None, **kwargs: object
    ) -> list[CommitInfo]:
        if path is not None:
            return [_COMMITS[path]]
        return [CommitInfo("head", "alice", "a@x.com", 1, _RECENT, "m")]

    async def list_commit_pulls(self, owner: str, repo: str, sha: str) -> list[int]:
        return _PULLS.get(sha, [])

    async def get_pull_request_reviews(self, owner: str, repo: str, number: int) -> list[ReviewInfo]:
        return _REVIEWS.get(number, [])

    async def aclose(self) -> None:
        pass


def _patch(monkeypatch: pytest.MonkeyPatch, ai_probs: dict[str, float]) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_ai(file_map: dict[str, str]) -> dict[str, float]:
        return ai_probs

    monkeypatch.setattr(knowledge_debt_detection, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(knowledge_debt_detection, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(gemini_stack_service, "estimate_ai_generation", _fake_ai)


def _request() -> KnowledgeDebtDetectionRequest:
    return KnowledgeDebtDetectionRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.KNOWLEDGE_DEBT_DETECTION,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        requested_by="user",
        project_id=str(uuid.uuid4()),
    )


async def _seed_job(session_maker: async_sessionmaker, job_id: str) -> None:
    async with session_maker() as session:
        session.add(
            Job(
                id=uuid.UUID(job_id), job_type=JobType.KNOWLEDGE_DEBT_DETECTION, status=JobStatus.PROCESSING, payload={}
            )
        )
        await session.commit()


async def _seed_kc(session_maker: async_sessionmaker, project_id: str) -> None:
    """Seed a kc_analysis run + file_kc for pkg/ai.py (aggregate + carol/dave dev rows)."""
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=uuid.UUID(project_id),
            commit_sha="kc",
            kind=JobType.KC_ANALYSIS.value,
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                FileKc(run_id=run.id, file_path="pkg/ai.py", kc=0.8, mastery="star"),  # aggregate
                FileKc(
                    run_id=run.id,
                    file_path="pkg/ai.py",
                    dev_id=uuid.uuid4(),
                    github_handle="carol",
                    kc=0.75,
                    mastery="star",
                    certified_via="authorship",
                ),
                FileKc(
                    run_id=run.id,
                    file_path="pkg/ai.py",
                    github_handle="dave",
                    kc=0.31,
                    mastery="black_hole",
                    certified_via="review",
                ),
            ]
        )
        await session.commit()


async def test_process_detects_each_reason_and_joins_kc(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch(monkeypatch, {"pkg/ai.py": 0.9})
    request = _request()
    await _seed_job(session_maker, request.job_id)
    await _seed_kc(session_maker, request.project_id)

    async with session_maker() as session:
        result = await knowledge_debt_detection.process(request, PipelineContext(session=session))

    assert result.detected == 3
    assert result.reasons == {"ai_generated": 1, "author_left": 1, "no_review": 1}

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        debts = {
            d.reason: d
            for d in (await session.execute(select(KnowledgeDebt).where(KnowledgeDebt.run_id == run.id)))
            .scalars()
            .all()
        }
        assert set(debts) == {"ai_generated", "author_left", "no_review"}
        ai_debt = debts["ai_generated"]
        assert ai_debt.file_path == "pkg/ai.py"
        assert ai_debt.ai_generation_prob == 0.9
        assert ai_debt.knowledge_coverage == 0.8  # joined from file_kc aggregate

        assigned = (
            (await session.execute(select(AssignedDeveloper).where(AssignedDeveloper.debt_id == ai_debt.id)))
            .scalars()
            .all()
        )
        by_handle = {a.github_handle: a for a in assigned}
        assert by_handle["carol"].coverage == 0.75  # 理解者: authorship かつ coverage>=0.7
        assert by_handle["carol"].certified_via == "authorship"
        assert by_handle["dave"].coverage == 0.31  # 形式レビューのみ: review / coverage<0.4
        assert by_handle["dave"].certified_via == "review"


async def test_process_is_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch, {"pkg/ai.py": 0.9})
    request = _request()
    await _seed_job(session_maker, request.job_id)
    await _seed_kc(session_maker, request.project_id)

    async with session_maker() as session:
        await knowledge_debt_detection.process(request, PipelineContext(session=session))
    async with session_maker() as session:
        await knowledge_debt_detection.process(request, PipelineContext(session=session))

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        debts = (
            await session.execute(select(func.count()).select_from(KnowledgeDebt).where(KnowledgeDebt.run_id == run.id))
        ).scalar_one()
        assert debts == 3  # upsert, not duplicated
        ai_debt = (
            await session.execute(
                select(KnowledgeDebt).where(KnowledgeDebt.run_id == run.id, KnowledgeDebt.reason == "ai_generated")
            )
        ).scalar_one()
        assigned = (
            await session.execute(
                select(func.count()).select_from(AssignedDeveloper).where(AssignedDeveloper.debt_id == ai_debt.id)
            )
        ).scalar_one()
        assert assigned == 2  # carol + dave, not duplicated
