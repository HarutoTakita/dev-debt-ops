"""service feature_clustering pipeline (issue 052): clusters → features/feature_files, idempotent.

GitHub + Gemini are mocked. Asserts features/feature_files are upserted under an analysis_run,
only real tree paths are accepted, and a redelivery (same job_id) does not duplicate the set.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.agents.budget import RunBudget
from service.agents.feature_agent import build_feature_agent
from service.pipelines import feature_clustering
from service.services import feature_authoring, gemini_stack_service
from service.services.github_git_client import CommitInfo, FileContent, TreeItem
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, Job, LearningPlan, QuizSession
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

    async def _fake_cluster(
        paths: list[str], edges: list[tuple[str, str]], *, owner: str, repo: str, descriptors: dict | None = None
    ) -> list[dict]:
        return clusters

    monkeypatch.setattr(feature_clustering, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(feature_clustering, "GitHubGitClient", lambda access_token: _FakeClient(_FILES))
    # 機能クラスタリングはエージェント経由（issue 263）。パイプラインテストでは orchestrator を直接差し替える。
    monkeypatch.setattr(feature_clustering.feature_authoring, "cluster_features_capability_first", _fake_cluster)


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


async def test_process_uses_provided_clusters_without_model(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """issue 268 (agent-first): when clusters are provided (Base Analysis Agent output), the pipeline
    formats/persists them directly and does NOT call the clustering model; tree paths are still validated."""

    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    monkeypatch.setattr(feature_clustering, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(feature_clustering, "GitHubGitClient", lambda access_token: _FakeClient(_FILES))
    called = {"n": 0}

    async def _should_not_run(*_a: object, **_k: object) -> list[dict]:
        called["n"] += 1
        return []

    monkeypatch.setattr(feature_clustering.feature_authoring, "cluster_features_agentic", _should_not_run)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await feature_clustering.process(request, PipelineContext(session=session), clusters=_CLUSTERS)
        await session.commit()

    assert called["n"] == 0  # the clustering model was skipped — base output used directly
    assert result.feature_count == 2
    assert result.file_count == 2  # the non-existent path is still dropped (tree validated)

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        features = {f.key for f in (await session.execute(select(Feature).where(Feature.run_id == run.id))).scalars()}
        assert features == {"auth", "billing"}


async def test_graph_community_expansion_grows_feature_along_edges(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """issue 293 (方針A): ``graph_edges`` re-aligns memberships — a file connected in the call graph
    joins the seeded feature's community and is persisted at the propagated (lower) confidence."""

    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    monkeypatch.setattr(feature_clustering, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(feature_clustering, "GitHubGitClient", lambda access_token: _FakeClient(_FILES))
    seed_clusters = [
        {"key": "auth", "name": "認証", "description": "", "files": [{"path": "src/auth.py", "confidence": 0.9}]}
    ]
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await feature_clustering.process(
            request,
            PipelineContext(session=session),
            clusters=seed_clusters,
            graph_edges=[("src/auth.py", "src/billing.py")],  # billing is graph-connected to the auth seed
        )
        await session.commit()

    assert result.feature_count == 1
    assert result.file_count == 2  # billing.py pulled into auth's community via the graph

    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        ff = (await session.execute(select(FeatureFile).where(FeatureFile.run_id == run.id))).scalars().all()
        by_path = {f.file_path: f for f in ff}
        assert set(by_path) == {"src/auth.py", "src/billing.py"}
        assert by_path["src/auth.py"].confidence == 0.9  # LLM-asserted confidence kept
        assert by_path["src/billing.py"].confidence == 0.5  # propagated member, lower confidence


class TestPathRecoveryAndBackfill:
    """機能に実ファイルが必ず割り当たる仕組み: 取りこぼし回収・近傍補完・空機能除去（純関数）。"""

    def test_path_resolver_recovers_near_miss(self) -> None:
        resolve = feature_clustering._path_resolver(["src/auth/login.py", "src/billing.py"])
        assert resolve("./src/auth/login.py") == "src/auth/login.py"  # ./ 正規化
        assert resolve("billing.py") == "src/billing.py"  # 一意 basename フォールバック
        assert resolve("does/not/exist.py") is None
        assert resolve("") is None

    def test_path_resolver_ambiguous_basename_unresolved(self) -> None:
        resolve = feature_clustering._path_resolver(["a/util.py", "b/util.py"])
        assert resolve("util.py") is None  # 複数一致は解決しない（誤マップ防止）

    def test_backfill_tops_up_from_unassigned_same_dir(self) -> None:
        clusters = [{"key": "auth", "files": [{"path": "src/auth/login.py", "confidence": 0.9}]}]
        source = ["src/auth/login.py", "src/auth/session.py", "src/auth/token.py", "src/auth/util.py"]
        feature_clustering._backfill_features(clusters, source)
        files = clusters[0]["files"]
        assert len(files) == feature_clustering._MIN_FEATURE_FILES  # 最低件数まで補完
        assert {f["path"] for f in files} <= set(source)
        added = [f for f in files if f["path"] != "src/auth/login.py"]
        assert all(f["confidence"] == feature_clustering._BACKFILL_CONFIDENCE for f in added)

    def test_backfill_does_not_steal_other_features_files(self) -> None:
        clusters = [
            {"key": "auth", "files": [{"path": "src/a.py", "confidence": 0.9}]},
            {"key": "billing", "files": [{"path": "src/b.py", "confidence": 0.9}]},
        ]
        feature_clustering._backfill_features(clusters, ["src/a.py", "src/b.py"])  # 未割当ファイル無し
        assert {f["path"] for f in clusters[0]["files"]} == {"src/a.py"}  # b.py を奪わない
        assert {f["path"] for f in clusters[1]["files"]} == {"src/b.py"}

    def test_backfill_skips_seedless_feature(self) -> None:
        clusters = [{"key": "ghost", "files": []}]
        feature_clustering._backfill_features(clusters, ["src/a.py", "src/b.py", "src/c.py"])
        assert clusters[0]["files"] == []  # アンカー無しは補完しない（永続化で除去される）


async def test_process_drops_feature_with_no_real_files(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """実ファイル 0 件の「幻の機能」は永続化しない（機能があるのにコードが無い状態を作らない）。"""
    clusters = [
        {"key": "auth", "name": "認証", "description": "", "files": [{"path": "src/auth.py", "confidence": 0.9}]},
        {"key": "ghost", "name": "幻", "description": "", "files": [{"path": "nowhere/x.py"}]},
    ]
    _patch(monkeypatch, clusters)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await feature_clustering.process(request, PipelineContext(session=session))
        await session.commit()

    assert result.feature_count == 1  # ghost は落ちる
    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        features = {f.key for f in (await session.execute(select(Feature).where(Feature.run_id == run.id))).scalars()}
        assert features == {"auth"}


async def test_process_recovers_basename_and_normalized_paths(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """LLM の basename/相対 path でも tree の実 path に解決して割り当てる（完全一致落ちで機能が空にならない）。"""
    clusters = [
        {
            "key": "auth",
            "name": "認証",
            "description": "",
            "files": [{"path": "auth.py", "confidence": 0.9}, {"path": "./src/billing.py"}],
        }
    ]
    _patch(monkeypatch, clusters)
    request = _request()
    await _seed_job(session_maker, request.job_id)

    async with session_maker() as session:
        result = await feature_clustering.process(request, PipelineContext(session=session))
        await session.commit()

    assert result.file_count == 2  # auth.py→src/auth.py, ./src/billing.py→src/billing.py
    async with session_maker() as session:
        run = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        ff = (await session.execute(select(FeatureFile).where(FeatureFile.run_id == run.id))).scalars().all()
        assert {f.file_path for f in ff} == {"src/auth.py", "src/billing.py"}


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


# --- agentic feature clustering (issue 263) --------------------------------


def test_feature_agent_save_tool_captures() -> None:
    """The agent's save_features tool records the features into the shared ``captured`` dict."""
    captured: dict = {}
    agent = build_feature_agent(budget=RunBudget(), captured=captured)
    (save_features,) = [t for t in agent.tools if getattr(t, "__name__", "") == "save_features"]
    save_features([{"key": "auth", "name": "Auth", "description": "d", "files": []}, {"no_key": 1}])
    assert [f["key"] for f in captured["features"]] == ["auth"]  # entries without a key are dropped


async def test_cluster_features_agentic_falls_back_when_agent_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the agent saves nothing (or errors), we fall back to the direct Gemini clustering."""

    async def _noop_run(**_kwargs: object) -> list[str]:
        return []  # agent produced no save_features call → captured stays empty

    async def _fake_direct(
        paths: list[str], edges: list[tuple[str, str]], *, descriptors: dict[str, str] | None = None
    ) -> list[dict]:
        return [{"key": "fallback", "name": "F", "description": "", "files": []}]

    monkeypatch.setattr(feature_authoring, "run_single_agent", _noop_run)
    monkeypatch.setattr(gemini_stack_service, "cluster_features", _fake_direct)
    out = await feature_authoring.cluster_features_agentic(["a.py"], [], owner="o", repo="r")
    assert [f["key"] for f in out] == ["fallback"]


async def test_cluster_features_agentic_empty_paths_is_noop() -> None:
    assert await feature_authoring.cluster_features_agentic([], [], owner="o", repo="r") == []


async def test_capability_first_builds_multi_membership_clusters(monkeypatch: pytest.MonkeyPatch) -> None:
    """capability-first: LLM が能力を列挙し、バッチ割当を集約して多重所属クラスタを構築する。"""

    async def _caps(fwp: list[tuple[str, str]]) -> list[dict]:
        return [
            {"key": "auth", "name": "認証", "description": ""},
            {"key": "quiz", "name": "クイズ", "description": ""},
        ]

    async def _assign(caps: list[dict], batch: list[tuple[str, str]]) -> dict[str, list[str]]:
        m = {"a.py": ["auth"], "b.py": ["auth", "quiz"], "c.py": ["quiz"]}  # b.py は多重所属
        return {p: m.get(p, []) for p, _ in batch}

    monkeypatch.setattr(gemini_stack_service, "propose_capabilities", _caps)
    monkeypatch.setattr(gemini_stack_service, "assign_files_to_capabilities", _assign)
    clusters = await feature_authoring.cluster_features_capability_first(
        ["a.py", "b.py", "c.py"], [], owner="o", repo="r", descriptors={"a.py": "auth stuff"}
    )
    by_key = {c["key"]: [f["path"] for f in c["files"]] for c in clusters}
    assert by_key["auth"] == ["a.py", "b.py"]
    assert by_key["quiz"] == ["b.py", "c.py"]  # b.py は auth と quiz の両方に登場（多重所属）


async def test_capability_first_falls_back_when_no_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """能力提案が空なら単発クラスタリングへフォールバック（挙動を後退させない）。"""

    async def _empty(fwp: list[tuple[str, str]]) -> list[dict]:
        return []

    async def _fallback(
        paths: list[str], edges: list[tuple[str, str]], *, owner: str, repo: str, descriptors: dict | None = None
    ) -> list[dict]:
        return [{"key": "fb", "name": "F", "description": "", "files": []}]

    monkeypatch.setattr(gemini_stack_service, "propose_capabilities", _empty)
    monkeypatch.setattr(feature_authoring, "cluster_features_agentic", _fallback)
    out = await feature_authoring.cluster_features_capability_first(["a.py"], [], owner="o", repo="r")
    assert [c["key"] for c in out] == ["fb"]


async def test_capability_first_falls_back_when_assignment_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """propose は成功したが全バッチが 1 件も割り当てない → 0 機能へ退行させず単発クラスタリングへフォールバック。"""

    async def _caps(fwp: list[tuple[str, str]]) -> list[dict]:
        return [{"key": "auth", "name": "認証", "description": ""}]

    async def _assign(caps: list[dict], batch: list[tuple[str, str]]) -> dict[str, list[str]]:
        return {}

    async def _fallback(
        paths: list[str], edges: list[tuple[str, str]], *, owner: str, repo: str, descriptors: dict | None = None
    ) -> list[dict]:
        return [{"key": "fb", "name": "F", "description": "", "files": [{"path": "a.py", "confidence": 0.9}]}]

    monkeypatch.setattr(gemini_stack_service, "propose_capabilities", _caps)
    monkeypatch.setattr(gemini_stack_service, "assign_files_to_capabilities", _assign)
    monkeypatch.setattr(feature_authoring, "cluster_features_agentic", _fallback)
    out = await feature_authoring.cluster_features_capability_first(["a.py"], [], owner="o", repo="r")
    assert [c["key"] for c in out] == ["fb"]  # 退行せずフォールバック結果


async def test_capability_first_resolves_name_when_key_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    """assign が key でなく能力名を返しても、正規化して canonical key に解決し割り当てる。"""

    async def _caps(fwp: list[tuple[str, str]]) -> list[dict]:
        return [{"key": "auth", "name": "認証", "description": ""}]

    async def _assign(caps: list[dict], batch: list[tuple[str, str]]) -> dict[str, list[str]]:
        return {p: ["認証"] for p, _ in batch}  # returns the NAME, not the key slug

    monkeypatch.setattr(gemini_stack_service, "propose_capabilities", _caps)
    monkeypatch.setattr(gemini_stack_service, "assign_files_to_capabilities", _assign)
    clusters = await feature_authoring.cluster_features_capability_first(["a.py"], [], owner="o", repo="r")
    by_key = {c["key"]: [f["path"] for f in c["files"]] for c in clusters}
    assert by_key["auth"] == ["a.py"]  # name→key 解決で割当が成立


# --- Phase 2a: incremental assignment + staleness ---------------------------

_V1_FILES = {f"src/auth/a{i}.py": "x = 1\n" for i in range(5)} | {f"src/billing/b{i}.py": "y = 2\n" for i in range(5)}
_V1_CLUSTERS = [
    {
        "key": "auth",
        "name": "認証",
        "description": "Auth",
        "files": [{"path": p, "confidence": 0.9} for p in _V1_FILES if "auth" in p],
    },
    {
        "key": "billing",
        "name": "課金",
        "description": "Billing",
        "files": [{"path": p, "confidence": 0.9} for p in _V1_FILES if "billing" in p],
    },
]
_NEW_FILE = "src/auth/a_new.py"
_V2_FILES = {**_V1_FILES, _NEW_FILE: "z = 3\n"}


def _patch_incr(monkeypatch: pytest.MonkeyPatch, files: dict[str, str], assignments: dict[str, list[str]]) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_cluster(paths, edges, *, owner, repo, descriptors=None):
        return _V1_CLUSTERS

    async def _fake_assign(caps, fwp):
        return dict(assignments)

    monkeypatch.setattr(feature_clustering, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(feature_clustering, "GitHubGitClient", lambda access_token: _FakeClient(files))
    monkeypatch.setattr(feature_clustering.feature_authoring, "cluster_features_capability_first", _fake_cluster)
    monkeypatch.setattr(feature_clustering.gemini_stack_service, "assign_files_to_capabilities", _fake_assign)


def _request_for(project_id: str) -> FeatureClusteringRequest:
    return FeatureClusteringRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.FEATURE_CLUSTERING,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        project_id=project_id,
        requested_by="user",
    )


async def _members(session_maker: async_sessionmaker, run_id: uuid.UUID) -> dict[str, set[str]]:
    async with session_maker() as session:
        rows = (
            await session.execute(
                select(Feature.key, FeatureFile.file_path).join(FeatureFile, FeatureFile.feature_id == Feature.id)
            )
        ).all()
    out: dict[str, set[str]] = {}
    for key, path in rows:
        out.setdefault(key, set()).add(path)
    return out


async def test_incremental_assigns_new_file_and_marks_stale(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """A small re-analysis assigns the new file to an existing feature (stable keys) and flags that
    feature's quiz/plan stale; an untouched feature stays intact and not stale."""
    project_id = str(uuid.uuid4())

    # Run 1: full cluster (no prior) → 10 files across auth/billing.
    _patch_incr(monkeypatch, _V1_FILES, {})
    req1 = _request_for(project_id)
    await _seed_job(session_maker, req1.job_id)
    async with session_maker() as session:
        await feature_clustering.process(req1, PipelineContext(session=session))
        await session.commit()

    # A developer already has a baseline quiz + plan for each feature (not stale).
    dev = uuid.uuid4()
    async with session_maker() as session:
        for key in ("auth", "billing"):
            session.add(
                QuizSession(
                    project_id=uuid.UUID(project_id),
                    developer_id=dev,
                    file_path="",
                    feature_key=key,
                    is_baseline=True,
                    status="completed",
                )
            )
            session.add(LearningPlan(project_id=uuid.UUID(project_id), developer_id=dev, feature_key=key))
        await session.commit()

    # Run 2: incremental — one new file, assigned to `auth`.
    _patch_incr(monkeypatch, _V2_FILES, {_NEW_FILE: ["auth"]})
    req2 = _request_for(project_id)
    await _seed_job(session_maker, req2.job_id)
    async with session_maker() as session:
        await feature_clustering.process(
            req2, PipelineContext(session=session), changed_paths={_NEW_FILE}, removed_paths=set(), head_sha="def456"
        )
        await session.commit()

    async with session_maker() as session:
        run2 = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.job_id == uuid.UUID(req2.job_id)))
        ).scalar_one()
        assert run2.commit_sha == "def456"
    members = await _members(session_maker, run2.id)
    assert set(members) == {"auth", "billing"}  # stable feature set (no re-cluster)
    assert _NEW_FILE in members["auth"]  # new file assigned to the existing feature
    assert len(members["auth"]) == 6
    assert len(members["billing"]) == 5  # untouched feature intact

    async with session_maker() as session:
        auth_q = (
            await session.execute(
                select(QuizSession).where(
                    QuizSession.project_id == uuid.UUID(project_id), QuizSession.feature_key == "auth"
                )
            )
        ).scalar_one()
        billing_q = (
            await session.execute(
                select(QuizSession).where(
                    QuizSession.project_id == uuid.UUID(project_id), QuizSession.feature_key == "billing"
                )
            )
        ).scalar_one()
        assert auth_q.stale is True  # auth's file set changed → 要再受験
        assert billing_q.stale is False  # billing unchanged


def test_reconcile_keys_reuses_prior_key_by_file_overlap() -> None:
    """A full re-cluster's fresh-keyed cluster adopts the prior feature's key when it covers mostly the
    same files (so quizzes/learning resolved by feature_key survive); a genuinely-new cluster keeps its
    key; and it never maps two clusters to the same prior key."""
    prior = {"auth": {"a1.py", "a2.py", "a3.py"}, "billing": {"b1.py", "b2.py"}}
    clusters = [
        {"key": "authentication", "name": "認証", "files": [{"path": p} for p in ["a1.py", "a2.py", "a3.py"]]},
        {"key": "payments", "name": "決済", "files": [{"path": "b1.py"}, {"path": "b2.py"}]},
        {"key": "brand-new", "name": "新機能", "files": [{"path": "n1.py"}, {"path": "n2.py"}]},
    ]
    remapped = feature_clustering._reconcile_keys(clusters, prior)
    assert remapped == 2
    keys = [c["key"] for c in clusters]
    assert keys == ["auth", "billing", "brand-new"]  # matched→prior key, new→unchanged


def test_reconcile_keys_noop_without_prior() -> None:
    clusters = [{"key": "x", "files": [{"path": "a.py"}]}]
    assert feature_clustering._reconcile_keys(clusters, {}) == 0
    assert clusters[0]["key"] == "x"
