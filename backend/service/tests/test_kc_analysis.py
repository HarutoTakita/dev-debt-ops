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
from service.services import code_analysis
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

        # authorship KC = min(share,1.0) × 初期KC推定（規模ベース: 極小/ボイラープレート=高い / 大=低い）。
        # 旧仕様の一律 0.35 上限は撤廃。a.py は極小なので init_kc は最大寄り（0.9）。
        f_a = kc_analysis._initial_kc_factor("pkg/a.py", _FILES["pkg/a.py"])

        # alice's 0.7 blame share × 高めの初期KC(小さいファイル) → dim_star 域まで上がる。
        alice_a = by[("pkg/a.py", _ALICE, "alice")]
        assert alice_a.kc == pytest.approx(0.7 * f_a, abs=1e-3)
        assert alice_a.mastery == "dim_star"
        assert alice_a.certified_via == "authorship"

        # bob is unmatched → dev_id None but github_handle preserved (no fabricated user link).
        bob_a = by[("pkg/a.py", None, "bob")]
        assert bob_a.kc == pytest.approx(0.3 * f_a, abs=1e-3)
        assert bob_a.mastery == "black_hole"

        # aggregate row: dev_id None, handle None, kc = max(dev kcs) = alice's → dim_star.
        agg_a = by[("pkg/a.py", None, None)]
        assert agg_a.kc == pytest.approx(0.7 * f_a, abs=1e-3)
        assert agg_a.mastery == "dim_star"

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


def test_select_source_paths_is_language_fair() -> None:
    # Round-robin across language buckets so .py doesn't starve the cap and hide .ts/.svelte
    # (fixes: 理解度マップに Python しか出ない). Vendored paths are filtered out.
    paths = [f"backend/{i}.py" for i in range(10)] + [
        "frontend/a.ts",
        "frontend/b.svelte",
        "frontend/node_modules/x.ts",
    ]
    picked = code_analysis.select_source_paths(paths, 4)
    assert len(picked) == 4
    assert any(p.endswith(".ts") for p in picked)
    assert any(p.endswith(".svelte") for p in picked)
    assert all("node_modules" not in p for p in picked)  # vendored dropped


def test_select_source_paths_honours_limit_and_covers_all_when_small() -> None:
    paths = ["a.py", "b.ts", "c.svelte"]
    assert set(code_analysis.select_source_paths(paths, 10)) == set(paths)  # all fit under the cap


def _patch_custom(
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str | None],
    blames: dict[str, list],
    resolve,
) -> None:
    """Patch kc_analysis I/O with a caller-supplied file/blame map (content may be None = unfetched)."""

    class _C:
        async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
            return [TreeItem(path=p, type="blob", size=len(c or "")) for p, c in files.items()]

        async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
            return FileContent(path=path, content=files[path], sha="sha", size=len(files[path] or ""))

        async def get_blame(self, owner: str, repo: str, path: str, ref: str = "main") -> list:
            return blames.get(path, [])

        async def list_commits(self, owner: str, repo: str, **kwargs: object) -> list[CommitInfo]:
            return [CommitInfo("abc123", "alice", "a@x.com", 1, "2026-01-01T00:00:00Z", "msg")]

        async def aclose(self) -> None:
            pass

    async def _mint(github: GitHubRef) -> str:
        return "tok"

    monkeypatch.setattr(kc_analysis, "_mint_installation_token", _mint)
    monkeypatch.setattr(kc_analysis, "GitHubGitClient", lambda access_token: _C())
    monkeypatch.setattr(kc_analysis, "resolve_author_user_id", resolve)


async def test_unfetched_file_is_not_treated_as_understood(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """内容取得に失敗した（大きすぎ/バイナリ）ファイルは行数 0 → 高 KC(理解済み) に誤反転させず floor に倒す。"""

    async def _resolve(session: object, identity: AuthorIdentity) -> uuid.UUID | None:
        return _ALICE if identity.github_user_id == 1 else None

    _patch_custom(
        monkeypatch,
        files={"pkg/big.py": None},  # content 取得不可
        blames={"pkg/big.py": [BlameRange(1, 500, "s", "alice", "a@x.com", 1)]},
        resolve=_resolve,
    )
    request = _request()
    await _seed_job(session_maker, request.job_id)
    async with session_maker() as session:
        await kc_analysis.process(request, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        run = (
            await session.execute(
                select(kc_analysis.AnalysisRun).where(kc_analysis.AnalysisRun.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        rows = {
            (r.file_path, r.dev_id, r.github_handle): r
            for r in (await session.execute(select(FileKc).where(FileKc.run_id == run.id))).scalars().all()
        }
        alice = rows[("pkg/big.py", _ALICE, "alice")]
        assert alice.kc == pytest.approx(1.0 * kc_analysis._KC_INITIAL_FLOOR, abs=1e-3)  # 0.9 ではなく floor
        assert alice.mastery == "black_hole"  # 理解済み(star/dim_star)にならない


async def test_login_less_author_folds_into_aggregate(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """dev_id も login も無い著者は per-dev 行を書かず（集約行スロットと衝突するため）、集約 KC にのみ反映する。"""

    async def _resolve(session: object, identity: AuthorIdentity) -> uuid.UUID | None:
        return None  # 未マッチ

    _patch_custom(
        monkeypatch,
        files={"pkg/anon.py": "X = 1\n"},
        blames={"pkg/anon.py": [BlameRange(1, 10, "s5", None, "d@x.com", None)]},  # login=None, id=None
        resolve=_resolve,
    )
    request = _request()
    await _seed_job(session_maker, request.job_id)
    async with session_maker() as session:
        result = await kc_analysis.process(request, PipelineContext(session=session))
        await session.commit()

    assert result.file_kc_count == 1  # 集約行のみ（衝突する per-dev 行は書かない・二重計上しない）

    async with session_maker() as session:
        run = (
            await session.execute(
                select(kc_analysis.AnalysisRun).where(kc_analysis.AnalysisRun.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        rows = (await session.execute(select(FileKc).where(FileKc.run_id == run.id))).scalars().all()
        assert len(rows) == 1
        agg = rows[0]
        assert (agg.dev_id, agg.github_handle) == (None, None)
        assert agg.kc > 0.0  # 著者の寄与が集約に反映（0 にクロバーされない）
        assert agg.mastery != "unexplored"  # has_contact=True（コミット履歴あり）


def test_select_source_paths_is_area_fair_not_starving_subsystems() -> None:
    # 大きい area（backend/api）がアルファベット順で言語枠を独占し、別サブシステム（backend/service）が
    # まるごと選外になる回帰を防ぐ（実測バグ: backend/service が 1 件も選ばれなかった）。
    paths = [f"backend/api/app/mod{i}.py" for i in range(60)] + [
        f"backend/service/service/pipelines/p{i}.py" for i in range(10)
    ]
    picked = code_analysis.select_source_paths(paths, 20)
    assert any(p.startswith("backend/service/") for p in picked)  # service サブシステムが選ばれる
    assert any(p.startswith("backend/api/") for p in picked)
