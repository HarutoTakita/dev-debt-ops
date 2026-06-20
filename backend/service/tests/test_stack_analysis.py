"""stack-analysis pipeline: tool logic, ``process`` (method-B mint), handler + idempotency.

GitHub and Vertex AI are mocked — the ADK ``Runner`` is never actually driven; instead
``run_stack_analysis`` is patched with a fake that upserts a ``TechStack`` (standing in for
the agent's ``save_stack``), so the tests exercise the service plumbing (token mint, DB
write, Job lifecycle, idempotency) without external calls.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from service.pipelines import stack_analysis
from service.services.github_app import GitHubAppService
from service.services.github_git_client import FileContent, TreeItem
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import Job, TechStack
from shared.pipelines.context import PipelineContext
from shared.schemas.stack_analysis import GitHubRef, StackAnalysisRequest

_CATS = ("frameworks", "databases", "auth", "container", "infra", "cicd", "monitoring", "testing", "other")


def _classification() -> dict:
    return {"languages": [{"name": "Python", "confidence": "high"}], "categories": {k: [] for k in _CATS}}


# ---------------------------------------------------------------------------
# tool logic (GitHub client + Gemini mocked)
# ---------------------------------------------------------------------------


class TestIsKeyFile:
    def test_nested_package_json(self) -> None:
        assert stack_analysis._is_key_file("frontend/package.json")

    def test_github_workflow(self) -> None:
        assert stack_analysis._is_key_file(".github/workflows/ci.yml")

    def test_source_file_is_not_key(self) -> None:
        assert not stack_analysis._is_key_file("src/main.ts")


class TestTools:
    async def test_list_key_files_filters_tree(self) -> None:
        client = AsyncMock()
        client.get_repository_tree.return_value = [
            TreeItem(path="package.json", type="blob", size=100),
            TreeItem(path="src/main.ts", type="blob", size=500),
            TreeItem(path="src", type="tree", size=None),
        ]
        list_key_files, _, _, _ = stack_analysis.build_tools(client, AsyncMock())
        result = await list_key_files("owner", "repo", "main")
        assert result == ["package.json"]

    async def test_read_file_truncates(self) -> None:
        client = AsyncMock()
        client.get_file_content.return_value = FileContent(path="big.tf", content="x" * 10_000, sha="s", size=10_000)
        _, read_file, _, _ = stack_analysis.build_tools(client, AsyncMock())
        result = await read_file("owner", "repo", "big.tf")
        assert "(truncated)" in result
        assert len(result) <= 5_100

    async def test_classify_stack_delegates_to_gemini(self, mocker) -> None:
        mocker.patch.object(stack_analysis, "analyze_tech_stack", AsyncMock(return_value=_classification()))
        _, _, classify_stack, _ = stack_analysis.build_tools(AsyncMock(), AsyncMock())
        result = await classify_stack({"pyproject.toml": "[project]"})
        assert result["languages"][0]["name"] == "Python"

    async def test_save_stack_upserts(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            _, _, _, save_stack = stack_analysis.build_tools(AsyncMock(), session)
            msg = await save_stack("acme", "rosetta", "main", _classification())
            await session.commit()  # save_stack now flushes; run_task owns the commit (issue-042)
        assert "acme/rosetta" in msg
        async with session_maker() as session:
            row = (await session.execute(_select_tech_stack("acme", "rosetta"))).scalar_one_or_none()
            assert row is not None
            assert row.languages[0]["name"] == "Python"


# ---------------------------------------------------------------------------
# process() — method B token mint + result shape
# ---------------------------------------------------------------------------


def _select_tech_stack(owner: str, repo: str):
    from sqlalchemy import select

    return select(TechStack).where(TechStack.owner == owner, TechStack.repo == repo)


def _fake_run_writes_stack(trace: list[str]):
    """Return a fake run_stack_analysis that upserts a TechStack (like the agent's save_stack)."""

    async def _fake(github_client, session, owner, repo, branch="main") -> list[str]:
        session.add(
            TechStack(
                owner=owner,
                repo=repo,
                analyzed_at=datetime.now(UTC),
                languages=_classification()["languages"],
                categories=_classification()["categories"],
            )
        )
        await session.commit()
        return trace

    return _fake


async def test_process_mints_token_and_returns_result(session_maker: async_sessionmaker[AsyncSession], mocker) -> None:
    mint = mocker.patch.object(GitHubAppService, "get_installation_token", AsyncMock(return_value="ghs_token"))
    trace = ["[call] list_key_files(...)", "[done] list_key_files", "[summary] done"]
    mocker.patch.object(stack_analysis, "run_stack_analysis", _fake_run_writes_stack(trace))

    request = StackAnalysisRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.STACK_ANALYSIS,
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=12345678),
        requested_by=str(uuid.uuid4()),
    )

    async with session_maker() as session:
        result = await stack_analysis.process(request, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    # Method B: the token was minted in the service from the installation id (no payload secret).
    mint.assert_awaited_once_with(12345678)
    assert result.status == ResultStatus.COMPLETED
    assert result.agent_trace == trace
    assert result.languages[0].name == "Python"


# ---------------------------------------------------------------------------
# /tasks/stack_analysis handler — Job lifecycle + idempotency
# ---------------------------------------------------------------------------


async def _seed_job(
    session_maker, *, status: JobStatus = JobStatus.QUEUED, result_data: dict | None = None
) -> uuid.UUID:
    async with session_maker() as session:
        job = Job(job_type=JobType.STACK_ANALYSIS, status=status, payload={}, result_data=result_data)
        session.add(job)
        await session.commit()
        return job.id


def _task_body(job_id: uuid.UUID) -> dict:
    return {
        "jobId": str(job_id),
        "jobType": JobType.STACK_ANALYSIS.value,
        "owner": "acme",
        "repo": "rosetta",
        "branch": "main",
        "requestedBy": str(uuid.uuid4()),
        "github": {"installationId": 12345678},
    }


async def test_handler_completes_job_and_writes_tech_stack(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession], mocker
) -> None:
    mocker.patch.object(GitHubAppService, "get_installation_token", AsyncMock(return_value="ghs_token"))
    trace = ["[call] list_key_files(...)", "[done] save_stack", "[summary] 完了"]
    mocker.patch.object(stack_analysis, "run_stack_analysis", _fake_run_writes_stack(trace))

    job_id = await _seed_job(session_maker)
    resp = await client.post(f"/tasks/{JobType.STACK_ANALYSIS.value}", json=_task_body(job_id))
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    async with session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.result_data is not None
        assert job.result_data["agentTrace"] == trace
        assert job.result_data["languages"][0]["name"] == "Python"
        ts = (await session.execute(_select_tech_stack("acme", "rosetta"))).scalar_one_or_none()
        assert ts is not None


async def test_handler_idempotent_on_redelivery(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession], mocker
) -> None:
    """A redelivered, already-COMPLETED job must not re-run the agent (at-least-once)."""
    mocker.patch.object(GitHubAppService, "get_installation_token", AsyncMock(return_value="ghs_token"))
    spy = mocker.patch.object(stack_analysis, "run_stack_analysis", AsyncMock(return_value=["x"]))

    job_id = await _seed_job(session_maker, status=JobStatus.COMPLETED, result_data={"agentTrace": ["original"]})
    resp = await client.post(f"/tasks/{JobType.STACK_ANALYSIS.value}", json=_task_body(job_id))
    assert resp.status_code == 200

    spy.assert_not_called()
    async with session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.result_data == {"agentTrace": ["original"]}
