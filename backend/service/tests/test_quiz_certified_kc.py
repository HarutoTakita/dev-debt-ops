"""issue 053: quiz grading reflects the score into file_kc (certified_via="quiz", uncapped)."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import quiz_grading
from service.services import gemini_stack_service
from service.services.github_git_client import FileContent
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, FileKc, QuizResult, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGradingRequest
from shared.schemas.stack_analysis import GitHubRef


class _FakeClient:
    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        return FileContent(path=path, content="def f(): pass\n", sha="s", size=10)

    async def aclose(self) -> None:
        return None


def _patch(monkeypatch: pytest.MonkeyPatch, score: float) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_grade(payload: str) -> dict:
        return {"score": score, "understood": [{"id": "c1", "label": "ok"}], "gap_concepts": []}

    monkeypatch.setattr(quiz_grading, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(quiz_grading, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(gemini_stack_service, "grade_quiz", _fake_grade)


async def _seed_kc_run(session_maker: async_sessionmaker, project_id: uuid.UUID) -> uuid.UUID:
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_session(
    session_maker: async_sessionmaker, *, project_id: uuid.UUID, developer_id: uuid.UUID
) -> uuid.UUID:
    async with session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=developer_id,
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            status="grading",
            questions=[{"id": "q1", "kind": "free_text", "prompt": "?", "difficulty": "L1"}],
            answer_key={"q1": {"answer": "a", "rubric": "r"}},
            source_kc=0.2,
        )
        session.add(qs)
        await session.commit()
        return qs.id


def _request(session_id: uuid.UUID, project_id: uuid.UUID) -> QuizGradingRequest:
    return QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(session_id),
        project_id=str(project_id),
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )


async def test_grading_certifies_kc_to_star(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    """A passing quiz writes file_kc certified_via='quiz' uncapped → star (authorship can't, issue 053)."""
    _patch(monkeypatch, 0.9)
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    run_id = await _seed_kc_run(session_maker, project_id)
    sid = await _seed_session(session_maker, project_id=project_id, developer_id=developer_id)

    async with session_maker() as session:
        result = await quiz_grading.process(_request(sid, project_id), PipelineContext(session=session))
        await session.commit()

    assert result.kc_after == 0.9
    assert result.kc_before == 0.0
    async with session_maker() as session:
        dev_row = (
            await session.execute(
                select(FileKc).where(
                    FileKc.run_id == run_id, FileKc.file_path == "src/a.py", FileKc.dev_id == developer_id
                )
            )
        ).scalar_one()
        assert dev_row.certified_via == "quiz"
        assert dev_row.kc == 0.9
        assert dev_row.mastery == "star"  # > 0.6 authorship ceiling
        # aggregate row re-derived to the max dev KC.
        agg = (
            await session.execute(
                select(FileKc).where(
                    FileKc.run_id == run_id,
                    FileKc.file_path == "src/a.py",
                    FileKc.dev_id.is_(None),
                    FileKc.github_handle.is_(None),
                )
            )
        ).scalar_one()
        assert agg.kc == 0.9

    # quiz_results echoes the real KC delta.
    async with session_maker() as session:
        qr = (await session.execute(select(QuizResult).where(QuizResult.session_id == sid))).scalar_one()
        assert qr.kc_after == 0.9


async def test_grading_creates_kc_row_for_blameless_file(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """No prior file_kc row (solo author / non-coding PM) → a fresh quiz-certified row is created."""
    _patch(monkeypatch, 0.8)
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    run_id = await _seed_kc_run(session_maker, project_id)
    sid = await _seed_session(session_maker, project_id=project_id, developer_id=developer_id)

    async with session_maker() as session:
        await quiz_grading.process(_request(sid, project_id), PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        rows = (
            (await session.execute(select(FileKc).where(FileKc.run_id == run_id, FileKc.dev_id == developer_id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].kc == 0.8


async def test_reflect_quiz_kc_is_idempotent_and_never_lowers(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """Re-grading with a lower score keeps the higher KC (max) and does not duplicate rows."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    run_id = await _seed_kc_run(session_maker, project_id)

    async with session_maker() as session:
        await quiz_grading._reflect_quiz_kc(
            session, project_id=project_id, file_path="src/a.py", developer_id=developer_id, score=0.9
        )
        await session.commit()
    async with session_maker() as session:
        before, after = await quiz_grading._reflect_quiz_kc(
            session, project_id=project_id, file_path="src/a.py", developer_id=developer_id, score=0.5
        )
        await session.commit()

    assert before == 0.9  # the previously earned KC
    assert after == 0.9  # max keeps the higher value
    async with session_maker() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(FileKc).where(FileKc.run_id == run_id, FileKc.dev_id == developer_id)
            )
        ).scalar_one()
        assert count == 1
