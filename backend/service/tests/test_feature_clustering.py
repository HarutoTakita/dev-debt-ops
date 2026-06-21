"""service feature_clustering pipeline (issue 052): clusters → features/feature_files, idempotent.

GitHub + Gemini are mocked. Asserts features/feature_files are upserted under an analysis_run,
only real tree paths are accepted, and a redelivery (same job_id) does not duplicate the set.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import feature_clustering
from service.services import gemini_stack_service
from service.services.github_git_client import CommitInfo, FileContent, TreeItem
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, Job
from shared.pipelines.context import PipelineContext
from shared.schemas.feature_clustering import FeatureClusteringRequest
from shared.schemas.stack_analysis import GitHubRef

_FILES = {"src/auth.py": "x = 1\n", "src/billing.py": "y = 2\n"}

_CLUSTERS = [
    {
        "key": "auth",
        "name": "認証",
        "description": "Authentication",
        "files": [{"path": "src/auth.py", "confidence": 0.9}, {"path": "does/not/exist.py", "confidence": 0.5}],
    },
    {"key": "billing", "name": "課金", "description": "Billing", "files": [{"path": "src/billing.py"}]},
]


class _FakeClient:
    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        return [TreeItem(path=p, type="blob", size=len(c)) for p, c in self._files.items()]

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
        return FileContent(path=path, content=self._files[path], sha="sha", size=len(self._files[path]))

    async def list_commits(self, owner: str, repo: str, **kwargs: object) -> list[CommitInfo]:
        return [CommitInfo("abc123", "alice", "a@x.com", 1, "2026-01-01T00:00:00Z", "msg")]

    async def aclose(self) -> None:
        return None


def _patch(monkeypatch: pytest.MonkeyPatch, clusters: list[dict]) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_cluster(paths: list[str], edges: list[tuple[str, str]]) -> list[dict]:
        return clusters

    monkeypatch.setattr(feature_clustering, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(feature_clustering, "GitHubGitClient", lambda access_token: _FakeClient(_FILES))
    monkeypatch.setattr(gemini_stack_service, "cluster_features", _fake_cluster)


async def _seed_job(session_maker: async_sessionmaker, job_id: str) -> None:
    async with session_maker() as session:
        session.add(
            Job(id=uuid.UUID(job_id), job_type=JobType.FEATURE_CLUSTERING, status=JobStatus.PROCESSING, payload={})
        )
        await session.commit()


def _request() -> FeatureClusteringRequest:
    return FeatureClusteringRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.FEATURE_CLUSTERING,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        project_id=str(uuid.uuid4()),
        requested_by="user",
    )


async def test_process_clusters_and_persists(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch(monkeypatch, _CLUSTERS)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await feature_clustering.process(request, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert result.feature_count == 2
    assert result.file_count == 2  # the non-existent path is dropped

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        assert run.kind == JobType.FEATURE_CLUSTERING.value
        feat_rows = (await session.execute(select(Feature).where(Feature.run_id == run.id))).scalars()
        features = {f.key: f for f in feat_rows}
        assert set(features) == {"auth", "billing"}
        assert features["auth"].name == "認証"
        ff = (await session.execute(select(FeatureFile).where(FeatureFile.run_id == run.id))).scalars().all()
        assert {(f.feature_id, f.file_path) for f in ff} == {
            (features["auth"].id, "src/auth.py"),
            (features["billing"].id, "src/billing.py"),
        }


async def test_process_is_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch, _CLUSTERS)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        await feature_clustering.process(request, PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        await feature_clustering.process(request, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        feat_count = (
            await session.execute(select(func.count()).select_from(Feature).where(Feature.run_id == run.id))
        ).scalar_one()
        ff_count = (
            await session.execute(select(func.count()).select_from(FeatureFile).where(FeatureFile.run_id == run.id))
        ).scalar_one()
        assert feat_count == 2
        assert ff_count == 2
