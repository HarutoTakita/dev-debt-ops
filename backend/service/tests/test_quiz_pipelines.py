"""issue 034: quiz generation + grading pipelines (GitHub/Gemini mocked)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import quiz_generation, quiz_grading
from service.services import gemini_stack_service, quiz_authoring
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

    async def _empty_agent(*args: object, **kwargs: object) -> dict:
        return {}  # force the agentic path to fall back to the (patched) direct generate_quiz

    monkeypatch.setattr(quiz_authoring, "_run_quiz_agent", _empty_agent)
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


async def test_grading_writes_result_and_completes(session_maker: async_sessionmaker) -> None:
    """Grading is rule-based (issue 298): a correct choice quiz scores 1.0 with no GitHub/Gemini."""
    sid = await _seed_session(
        session_maker,
        questions=[{"id": "q1", "kind": "multiple_choice", "prompt": "P1", "difficulty": "L1"}],
        answer_key={"q1": {"answer": "a", "rubric": ""}},
        status="grading",
    )
    async with session_maker() as session:
        session.add(QuizAnswer(session_id=sid, question_id="q1", value="a"))
        await session.commit()

    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        github=GitHubRef(installation_id=1),  # retained on schema; ignored by rule-based grading
        requested_by="u",
    )
    async with session_maker() as session:
        result = await quiz_grading.process(req, PipelineContext(session=session))
        await session.commit()  # run_task owns the commit in production (issue-042)

    assert result.score == 1.0
    assert result.kc_before == 0.2
    assert result.kc_after > 0.2  # no kc_analysis run to anchor → kc_after = score
    async with session_maker() as session:
        qs = (await session.execute(select(QuizSession).where(QuizSession.id == sid))).scalar_one()
        assert qs.status == "completed"
        qr = (await session.execute(select(QuizResult).where(QuizResult.session_id == sid))).scalar_one()
        assert qr.understood[0]["id"] == "q1"
        assert qr.gap_concepts == []


async def test_grading_offline_choice_quiz_without_github(session_maker: async_sessionmaker) -> None:
    """A choice-only quiz with no GitHub installation (id=0) is graded deterministically (issue 069).

    Nothing is patched: no token mint, no file fetch, no Gemini. If the offline branch were skipped,
    the un-patched GitHub/Gemini calls would blow up — so a clean pass proves the demo path is offline.
    """
    questions = [
        {"id": "q1", "kind": "multiple_choice", "prompt": "P1", "difficulty": "L1"},
        {"id": "q2", "kind": "multiple_select", "prompt": "P2", "difficulty": "L2"},
    ]
    answer_key = {"q1": {"answer": "a", "rubric": ""}, "q2": {"answer": ["a", "b"], "rubric": ""}}
    sid = await _seed_session(session_maker, questions=questions, answer_key=answer_key, status="grading")
    async with session_maker() as session:
        session.add(QuizAnswer(session_id=sid, question_id="q1", value="a"))
        session.add(QuizAnswer(session_id=sid, question_id="q2", value="b,a"))  # order-insensitive set match
        await session.commit()

    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        github=GitHubRef(installation_id=0),
        requested_by="u",
    )
    async with session_maker() as session:
        result = await quiz_grading.process(req, PipelineContext(session=session))
        await session.commit()

    assert result.score == 1.0
    async with session_maker() as session:
        qs = (await session.execute(select(QuizSession).where(QuizSession.id == sid))).scalar_one()
        assert qs.status == "completed"
        assert qs.score == 1.0
        qr = (await session.execute(select(QuizResult).where(QuizResult.session_id == sid))).scalar_one()
        assert qr.gap_concepts == []  # all correct
        assert {c["id"] for c in qr.understood} == {"q1", "q2"}


async def test_grading_offline_partial_score(session_maker: async_sessionmaker) -> None:
    """Offline grading scores the fraction correct and records the missed question as a gap."""
    questions = [
        {"id": "q1", "kind": "multiple_choice", "prompt": "P1", "difficulty": "L1"},
        {"id": "q2", "kind": "multiple_choice", "prompt": "P2", "difficulty": "L1"},
    ]
    answer_key = {"q1": {"answer": "a", "rubric": ""}, "q2": {"answer": "b", "rubric": ""}}
    sid = await _seed_session(session_maker, questions=questions, answer_key=answer_key, status="grading")
    async with session_maker() as session:
        session.add(QuizAnswer(session_id=sid, question_id="q1", value="a"))  # correct
        session.add(QuizAnswer(session_id=sid, question_id="q2", value="c"))  # wrong
        await session.commit()

    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(uuid.uuid4()),
        github=GitHubRef(installation_id=0),
        requested_by="u",
    )
    async with session_maker() as session:
        result = await quiz_grading.process(req, PipelineContext(session=session))
        await session.commit()

    assert result.score == 0.5
    async with session_maker() as session:
        qr = (await session.execute(select(QuizResult).where(QuizResult.session_id == sid))).scalar_one()
        assert [c["id"] for c in qr.gap_concepts] == ["q2"]


async def test_grading_idempotent_when_completed(session_maker: async_sessionmaker) -> None:
    """A completed session is not re-graded — the persisted score is echoed unchanged (issue-042)."""
    sid = await _seed_session(session_maker, status="completed")
    async with session_maker() as session:
        qs = (await session.execute(select(QuizSession).where(QuizSession.id == sid))).scalar_one()
        qs.score = 0.5
        session.add(qs)
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
    assert result.score == 0.5  # completed → echoed, not re-graded
