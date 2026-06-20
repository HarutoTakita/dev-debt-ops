"""issue 029: KC analysis — mastery thresholds + pipeline persistence (GitHub/authorship mocked).

Pure helpers (mastery_from_kc / aggregate_blame) are unit-tested. The pipeline ``process`` runs
against the test DB with GitHub blame and authorship matching mocked, asserting file_kc (dev +
aggregate + unmatched-author handle rows), dependencies (wormholes), mastery derivation, and
at-least-once idempotency.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import kc_analysis
from service.services.authorship import AuthorIdentity
from service.services.github_git_client import BlameRange, CommitInfo, FileContent, TreeItem
from shared.enums import JobStatus, JobType
from shared.models import Dependency, FileKc, Job
from shared.pipelines.context import PipelineContext
from shared.schemas.kc_analysis import KcAnalysisRequest
from shared.schemas.stack_analysis import GitHubRef

_ALICE = uuid.uuid4()


class TestMasteryFromKc:
    def test_star(self) -> None:
        assert kc_analysis.mastery_from_kc(0.7, has_contact=True) == "star"

    def test_dim_star(self) -> None:
        assert kc_analysis.mastery_from_kc(0.69, has_contact=True) == "dim_star"
        assert kc_analysis.mastery_from_kc(0.4, has_contact=True) == "dim_star"

    def test_black_hole_requires_contact(self) -> None:
        assert kc_analysis.mastery_from_kc(0.39, has_contact=True) == "black_hole"

    def test_unexplored_no_contact(self) -> None:
        assert kc_analysis.mastery_from_kc(0.0, has_contact=False) == "unexplored"
        assert kc_analysis.mastery_from_kc(0.9, has_contact=False) == "unexplored"


class TestAggregateBlame:
    def test_line_shares_sum_to_one(self) -> None:
        ranges = [
            BlameRange(1, 7, "s1", "alice", "a@x.com", 1),
            BlameRange(8, 10, "s2", "bob", "b@x.com", 2),
        ]
        shares = dict((ident.login, round(ratio, 3)) for ident, ratio in kc_analysis.aggregate_blame(ranges))
        assert shares == {"alice": 0.7, "bob": 0.3}

    def test_empty(self) -> None:
        assert kc_analysis.aggregate_blame([]) == []


# --- pipeline -------------------------------------------------------------

_FILES = {
    "pkg/a.py": "from pkg import b\n",  # imports b → wormhole a→b
    "pkg/b.py": "VALUE = 1\n",
    "pkg/lonely.py": "X = 1\n",  # no blame → unexplored aggregate
}
_BLAMES = {
    "pkg/a.py": [BlameRange(1, 7, "s1", "alice", "a@x.com", 1), BlameRange(8, 10, "s2", "bob", "b@x.com", 2)],
    "pkg/b.py": [BlameRange(1, 4, "s3", "carol", "c@x.com", 3), BlameRange(5, 10, "s4", "alice", "a@x.com", 1)],
    "pkg/lonely.py": [],
}


class _FakeClient:
    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        return [TreeItem(path=p, type="blob", size=len(c)) for p, c in _FILES.items()]

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
        return FileContent(path=path, content=_FILES[path], sha="sha", size=len(_FILES[path]))

    async def get_blame(self, owner: str, repo: str, path: str, ref: str = "main") -> list[BlameRange]:
        return _BLAMES[path]

    async def list_commits(self, owner: str, repo: str, **kwargs: object) -> list[CommitInfo]:
        return [CommitInfo("abc123", "alice", "a@x.com", 1, "2026-01-01T00:00:00Z", "msg")]

    async def aclose(self) -> None:
        pass


def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_resolve(session: object, identity: AuthorIdentity) -> uuid.UUID | None:
        return _ALICE if identity.github_user_id == 1 else None  # alice matched, others unmatched

    monkeypatch.setattr(kc_analysis, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(kc_analysis, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(kc_analysis, "resolve_author_user_id", _fake_resolve)


def _request() -> KcAnalysisRequest:
    return KcAnalysisRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.KC_ANALYSIS,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        requested_by="user",
        project_id=str(uuid.uuid4()),
    )


async def _seed_job(session_maker: async_sessionmaker, job_id: str) -> None:
    async with session_maker() as session:
        session.add(Job(id=uuid.UUID(job_id), job_type=JobType.KC_ANALYSIS, status=JobStatus.PROCESSING, payload={}))
        await session.commit()


async def test_process_computes_kc_and_wormholes(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch(monkeypatch)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await kc_analysis.process(request, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    # a.py: alice + bob(unmatched) + agg = 3; b.py: alice + carol(unmatched) + agg = 3; lonely: agg = 1.
    assert result.file_kc_count == 7
    assert result.dependency_count == 1

    async with session_maker() as session:
        run = (
            await session.execute(
                select(kc_analysis.AnalysisRun).where(kc_analysis.AnalysisRun.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        rows = (await session.execute(select(FileKc).where(FileKc.run_id == run.id))).scalars().all()
        by = {(r.file_path, r.dev_id, r.github_handle): r for r in rows}

        alice_a = by[("pkg/a.py", _ALICE, "alice")]
        assert round(alice_a.kc, 3) == 0.7
        assert alice_a.mastery == "star"
        assert alice_a.certified_via == "authorship"

        # bob is unmatched → dev_id None but github_handle preserved (no fabricated user link).
        bob_a = by[("pkg/a.py", None, "bob")]
        assert round(bob_a.kc, 3) == 0.3
        assert bob_a.mastery == "black_hole"

        # aggregate row: dev_id None, handle None, kc = max(dev kcs).
        agg_a = by[("pkg/a.py", None, None)]
        assert round(agg_a.kc, 3) == 0.7
        assert agg_a.mastery == "star"

        # lonely.py has no blame → unexplored aggregate, no dev rows.
        agg_lonely = by[("pkg/lonely.py", None, None)]
        assert agg_lonely.mastery == "unexplored"

        deps = (await session.execute(select(Dependency).where(Dependency.run_id == run.id))).scalars().all()
        assert {(d.from_path, d.to_path) for d in deps} == {("pkg/a.py", "pkg/b.py")}


async def test_process_is_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        await kc_analysis.process(request, PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        await kc_analysis.process(request, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        run = (
            await session.execute(
                select(kc_analysis.AnalysisRun).where(kc_analysis.AnalysisRun.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        file_kc = (
            await session.execute(select(func.count()).select_from(FileKc).where(FileKc.run_id == run.id))
        ).scalar_one()
        deps = (
            await session.execute(select(func.count()).select_from(Dependency).where(Dependency.run_id == run.id))
        ).scalar_one()
        assert file_kc == 7  # upsert, not duplicated
        assert deps == 1
