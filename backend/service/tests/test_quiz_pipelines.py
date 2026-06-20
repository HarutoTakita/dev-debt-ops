"""issue 034: quiz generation + grading pipelines (GitHub/Gemini mocked)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import quiz_generation, quiz_grading
from service.services import gemini_stack_service
from service.services.github_git_client import FileContent
from shared.enums import JobType
from shared.models import QuizAnswer, QuizResult, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGenerationRequest, QuizGradingRequest
from shared.schemas.stack_analysis import GitHubRef


class _FakeClient:
    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        return FileContent(path=path, content="def f(): pass\n", sha="s", size=10)

    async def aclose(self) -> None:
        return None


def _patch_common(monkeypatch: pytest.MonkeyPatch, module) -> None:
    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    monkeypatch.setattr(module, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(module, "GitHubGitClient", lambda access_token: _FakeClient())


async def _seed_session(
    session_maker: async_sessionmaker, *, questions=None, answer_key=None, status="not_started"
) -> uuid.UUID:
    async with session_maker() as session:
        qs = QuizSession(
            project_id=uuid.uuid4(),
            developer_id=uuid.uuid4(),
            file_path="src/a.py",
            repo_full_name="acme/rosetta",
            status=status,
            questions=questions or [],
            answer_key=answer_key or {},
            source_kc=0.2,
        )
        session.add(qs)
        await session.commit()
        return qs.id


async def test_generation_fills_questions(monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker) -> None:
    _patch_common(monkeypatch, quiz_generation)

    async def _fake_gen(path: str, content: str) -> dict:
        return {
            "questions": [{"id": "q1", "kind": "free_text", "prompt": "?", "code_snippet": None, "difficulty": "L1"}],
            "answer_key": {"q1": {"answer": "a", "rubric": "r"}},
        }

    monkeypatch.setattr(gemini_stack_service, "generate_quiz", _fake_gen)
    sid = await _seed_session(session_maker)
    req = QuizGenerationRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GENERATION,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        file_path="src/a.py",
        repo_full_name="acme/rosetta",
        branch="main",
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )
    async with session_maker() as session:
        result = await quiz_generation.process(req, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)
    assert result.question_count == 1
    async with session_maker() as session:
        qs = (await session.execute(select(QuizSession).where(QuizSession.id == sid))).scalar_one()
        assert len(qs.questions) == 1
        assert qs.answer_key["q1"]["answer"] == "a"


async def test_grading_writes_result_and_completes(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch_common(monkeypatch, quiz_grading)

    async def _fake_grade(payload: str) -> dict:
        return {
            "score": 0.8,
            "understood": [{"id": "c1", "label": "ok"}],
            "gap_concepts": [{"id": "c2", "label": "gap"}],
        }

    monkeypatch.setattr(gemini_stack_service, "grade_quiz", _fake_grade)
    sid = await _seed_session(
        session_maker,
        questions=[{"id": "q1", "kind": "free_text", "prompt": "?", "difficulty": "L1"}],
        answer_key={"q1": {"answer": "a", "rubric": "r"}},
        status="grading",
    )
    async with session_maker() as session:
        session.add(QuizAnswer(session_id=sid, question_id="q1", value="my answer"))
        await session.commit()

    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )
    async with session_maker() as session:
        result = await quiz_grading.process(req, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert result.score == 0.8
    assert result.kc_before == 0.2
    assert result.kc_after > 0.2  # provisional bump toward 1.0
    async with session_maker() as session:
        qs = (await session.execute(select(QuizSession).where(QuizSession.id == sid))).scalar_one()
        assert qs.status == "completed"
        qr = (await session.execute(select(QuizResult).where(QuizResult.session_id == sid))).scalar_one()
        assert qr.understood[0]["id"] == "c1"
        assert qr.gap_concepts[0]["id"] == "c2"


async def test_grading_idempotent_when_completed(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    _patch_common(monkeypatch, quiz_grading)
    graded_calls = {"n": 0}

    async def _fake_grade(payload: str) -> dict:
        graded_calls["n"] += 1
        return {"score": 0.5, "understood": [], "gap_concepts": []}

    monkeypatch.setattr(gemini_stack_service, "grade_quiz", _fake_grade)
    sid = await _seed_session(session_maker, status="completed")
    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )
    async with session_maker() as session:
        await quiz_grading.process(req, PipelineContext(session=session))
    assert graded_calls["n"] == 0  # completed → not re-graded
