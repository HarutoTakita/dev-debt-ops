"""issue 036: agent-loop pipeline — read-and-narrate binding + idempotency (Gemini mocked)."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import agent_loop
from service.services import gemini_stack_service
from shared.enums import JobStatus, JobType
from shared.models import AgentActivity, AgentPipeline, AnalysisRun, CodeDebt, NarrativeEvidence, NarrativeStep
from shared.pipelines.context import PipelineContext
from shared.schemas.agent_loop import AgentLoopRequest
from shared.schemas.stack_analysis import GitHubRef


def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_narrative(kind: str, summary: str) -> dict:
        return {
            "headline": "コード負債を掘り起こした",
            "steps": [
                {"status": "scanning", "message": "リポジトリを走査した"},
                {"status": "analyzing", "message": "初出コミットまで遡った"},
                {"status": "succeeded", "message": "返済計画を立てた"},
            ],
        }

    monkeypatch.setattr(gemini_stack_service, "generate_agent_narrative", _fake_narrative)


async def _seed_findings(session_maker: async_sessionmaker, project_id: uuid.UUID) -> uuid.UUID:
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.CODE_DEBT_DETECTION.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        debt = CodeDebt(
            project_id=project_id,
            run_id=run.id,
            file_path="src/a.py",
            type="complexity",
            severity="high",
            code_debt_score=0.8,
            ai_generation_prob=0.9,
            archaeology_notes="循環的複雑度 24",
            related_pr="#5",
        )
        session.add(debt)
        await session.commit()
        return debt.id


def _request(project_id: uuid.UUID) -> AgentLoopRequest:
    return AgentLoopRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.CODE_DEBT_LOOP,
        project_id=str(project_id),
        owner="acme",
        repo="rosetta",
        branch="main",
        github=GitHubRef(installation_id=1),
        kind="code_debt",
        requested_by="u",
    )


async def test_loop_binds_pipeline_activity_and_evidence(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch(monkeypatch)
    project_id = uuid.uuid4()
    debt_id = await _seed_findings(session_maker, project_id)
    request = _request(project_id)

    async with session_maker() as session:
        result = await agent_loop.process(request, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert result.step_count == 3
    async with session_maker() as session:
        pipeline = (
            await session.execute(select(AgentPipeline).where(AgentPipeline.job_id == uuid.UUID(request.job_id)))
        ).scalar_one()
        assert len(pipeline.stages) == 5
        detect = next(s for s in pipeline.stages if s["key"] == "detect")
        assert detect["nodes"][0]["status"] == "succeeded"  # findings exist
        repay = next(s for s in pipeline.stages if s["key"] == "repay")
        assert repay["nodes"][0]["status"] == "pending"  # MVP: not auto-run

        activity = (
            await session.execute(select(AgentActivity).where(AgentActivity.pipeline_id == pipeline.id))
        ).scalar_one()
        assert activity.headline == "コード負債を掘り起こした"
        steps = (
            (
                await session.execute(
                    select(NarrativeStep).where(NarrativeStep.activity_id == activity.id).order_by(NarrativeStep.order)
                )
            )
            .scalars()
            .all()
        )
        assert [s.status for s in steps] == ["scanning", "analyzing", "succeeded"]
        # evidence is attached to the analyze step (order 1), with a cross-domain Matrix href.
        ev = (
            (await session.execute(select(NarrativeEvidence).where(NarrativeEvidence.step_id == steps[1].id)))
            .scalars()
            .all()
        )
        types = {e.type for e in ev}
        assert "first_commit" in types
        assert "ai_generated" in types  # ai_generation_prob 0.9
        assert "pr_review" in types  # related_pr #5
        assert all(e.href == f"/matrix/{debt_id}" for e in ev)


async def test_loop_idempotent(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch(monkeypatch)
    project_id = uuid.uuid4()
    await _seed_findings(session_maker, project_id)
    request = _request(project_id)

    async with session_maker() as session:
        await agent_loop.process(request, PipelineContext(session=session))
        await session.commit()
    async with session_maker() as session:
        await agent_loop.process(request, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(AgentPipeline).where(AgentPipeline.job_id == uuid.UUID(request.job_id))
            )
        ).scalar_one()
        assert count == 1  # not duplicated
