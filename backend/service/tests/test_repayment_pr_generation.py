"""issue 033: repayment-PR pipeline — refactor → PR → code_debt update, idempotent.

GitHub write methods and Gemini are mocked. Asserts the PR is opened, ``code_debts`` becomes
``in_pr`` with ``related_pr``, and a redelivery (already in_pr) skips re-creating the PR.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import repayment_pr_generation
from service.services import gemini_stack_service, repayment_refactor
from service.services.gemini_stack_service import _is_plausible_refactor
from service.services.github_git_client import FileContent
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, CodeDebt
from shared.pipelines.context import PipelineContext
from shared.schemas.repayment_pr_generation import RepaymentPrGenerationRequest
from shared.schemas.stack_analysis import GitHubRef


class _FakeClient:
    def __init__(self, existing_pr: tuple[int, str] | None = None) -> None:
        self.created_pr = False
        self.pr_title = ""
        self.branches: list[str] = []
        self._existing_pr = existing_pr  # simulate a prior partial run that already opened the PR

    async def find_open_pull_request(self, owner: str, repo: str, head: str) -> tuple[int, str] | None:
        return self._existing_pr

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        return FileContent(path=path, content="def f():\n    pass\n", sha="filesha", size=10)

    async def get_branch_sha(self, owner: str, repo: str, branch: str) -> str:
        return "basesha"

    async def create_branch(self, owner: str, repo: str, new_branch: str, from_sha: str) -> None:
        self.branches.append(new_branch)

    async def create_or_update_file(self, owner: str, repo: str, path: str, **kwargs: object) -> None:
        return None

    async def create_pull_request(self, owner: str, repo: str, **kwargs: object) -> tuple[int, str]:
        self.created_pr = True
        self.pr_title = str(kwargs.get("title") or "")
        return 42, "https://github.com/acme/rosetta/pull/42"

    async def aclose(self) -> None:
        return None


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_refactor(path: str, content: str, notes: str) -> dict[str, str]:
        return {"new_content": "def f():\n    return 1\n", "pr_title": "Repay", "pr_body": "fix"}

    async def _empty_agent(*args: object, **kwargs: object) -> dict:
        return {}  # force the agentic path to fall back to the (patched) direct generate_refactor

    monkeypatch.setattr(repayment_pr_generation, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(repayment_pr_generation, "GitHubGitClient", lambda access_token: fake)
    monkeypatch.setattr(repayment_refactor, "_run_refactor_agent", _empty_agent)
    monkeypatch.setattr(gemini_stack_service, "generate_refactor", _fake_refactor)


async def _seed_debt(session_maker: async_sessionmaker) -> uuid.UUID:
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=uuid.uuid4(), commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        debt = CodeDebt(
            project_id=run.project_id,
            run_id=run.id,
            file_path="src/a.py",
            type="complexity",
            severity="high",
            code_debt_score=0.8,
            status="open",
        )
        session.add(debt)
        await session.commit()
        return debt.id


def _request(debt_id: uuid.UUID) -> RepaymentPrGenerationRequest:
    return RepaymentPrGenerationRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.REPAYMENT_PR_GENERATION,
        debt_id=str(debt_id),
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=42),
        requested_by="user",
    )


async def test_process_opens_pr_and_marks_in_pr(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    debt_id = await _seed_debt(session_maker)

    async with session_maker() as session:
        result = await repayment_pr_generation.process(_request(debt_id), PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert fake.created_pr is True
    assert result.pr_number == 42
    assert result.pr_url == "https://github.com/acme/rosetta/pull/42"
    assert result.branch == f"devdebtops/fix-{str(debt_id)[:8]}"
    assert fake.pr_title.startswith("[DevDebtOps] ")  # 出所タグ（issue 227）

    async with session_maker() as session:
        debt = (await session.execute(select(CodeDebt).where(CodeDebt.id == debt_id))).scalar_one()
        assert debt.status == "in_pr"
        assert debt.related_pr == "https://github.com/acme/rosetta/pull/42"  # PR番号でなく URL（issue 227）


async def test_process_idempotent_when_already_in_pr(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    debt_id = await _seed_debt(session_maker)

    async with session_maker() as session:
        await repayment_pr_generation.process(_request(debt_id), PipelineContext(session=session))
        await session.commit()
    fake.created_pr = False  # reset; a redelivery must NOT open another PR
    async with session_maker() as session:
        result = await repayment_pr_generation.process(_request(debt_id), PipelineContext(session=session))
        await session.commit()

    assert fake.created_pr is False  # skipped
    assert result.pr_number is None
    async with session_maker() as session:
        debt = (await session.execute(select(CodeDebt).where(CodeDebt.id == debt_id))).scalar_one()
        assert debt.related_pr == "https://github.com/acme/rosetta/pull/42"  # unchanged (URL, issue 227)


async def test_process_reuses_existing_pr_when_debt_not_yet_in_pr(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """Partial-failure redelivery: the PR was opened but the debt row never committed (issue-043).

    The pipeline must reuse the existing PR (no duplicate / no 422) and finish marking the debt.
    """
    fake = _FakeClient(existing_pr=(42, "https://github.com/acme/rosetta/pull/42"))
    _patch(monkeypatch, fake)
    debt_id = await _seed_debt(session_maker)  # status still "open", no related_pr

    async with session_maker() as session:
        result = await repayment_pr_generation.process(_request(debt_id), PipelineContext(session=session))
        await session.commit()

    assert fake.created_pr is False  # did NOT open a second PR
    assert result.pr_number == 42
    async with session_maker() as session:
        debt = (await session.execute(select(CodeDebt).where(CodeDebt.id == debt_id))).scalar_one()
        assert debt.status == "in_pr"
        assert debt.related_pr == "https://github.com/acme/rosetta/pull/42"


def test_is_plausible_refactor_rejects_empty_and_runaway() -> None:
    """The prompt-injection size guard rejects empty / wildly oversized model output (issue-043)."""
    original = "def f():\n    return 1\n"
    assert _is_plausible_refactor(original, "def f():\n    return 2\n") is True
    assert _is_plausible_refactor(original, "   ") is False  # empty
    assert _is_plausible_refactor(original, "x" * (len(original) * 3 + 5000)) is False  # runaway rewrite
