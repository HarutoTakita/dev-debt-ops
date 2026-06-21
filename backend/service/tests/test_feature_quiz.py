"""service feature-scope quiz (issue 054): generation from feature_files + grading KC expansion."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from service.pipelines import quiz_generation, quiz_grading
from service.services import gemini_stack_service
from service.services.github_git_client import FileContent
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, FileKc, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGenerationRequest, QuizGradingRequest
from shared.schemas.stack_analysis import GitHubRef


class _FakeClient:
    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        return FileContent(path=path, content=f"# {path}\n", sha="s", size=10)

    async def aclose(self) -> None:
        return None


async def _seed_feature(session_maker: async_sessionmaker, project_id: uuid.UUID, files: list[str]) -> uuid.UUID:
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.FEATURE_CLUSTERING.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.flush()
        feat = Feature(project_id=project_id, run_id=run.id, key="auth", name="認証", description="Authentication")
        session.add(feat)
        await session.flush()
        for f in files:
            session.add(FeatureFile(run_id=run.id, feature_id=feat.id, file_path=f, confidence=0.9))
        await session.commit()
        return feat.id


async def _seed_kc_run(session_maker: async_sessionmaker, project_id: uuid.UUID) -> uuid.UUID:
    async with session_maker() as session:
        run = AnalysisRun(
            project_id=project_id, commit_sha="c", kind=JobType.KC_ANALYSIS.value, status=JobStatus.COMPLETED
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_feature_session(
    session_maker: async_sessionmaker, *, project_id: uuid.UUID, developer_id: uuid.UUID, feature_id: uuid.UUID
) -> uuid.UUID:
    async with session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=developer_id,
            file_path="src/auth.py",
            repo_full_name="acme/rosetta",
            granularity="feature",
            feature_id=feature_id,
            is_baseline=True,
            status="grading",
            questions=[{"id": "q1", "kind": "free_text", "prompt": "?", "difficulty": "L1"}],
            answer_key={"q1": {"answer": "a", "rubric": "r"}},
        )
        session.add(qs)
        await session.commit()
        return qs.id


async def test_generation_feature_scope_builds_quiz(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """A feature-scope session generates from its feature_files + description (issue 054)."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    feature_id = await _seed_feature(session_maker, project_id, ["src/auth.py", "src/token.py"])

    seen: dict[str, str] = {}

    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_gen(label: str, content: str) -> dict:
        seen["label"] = label
        seen["content"] = content
        return {"questions": [{"id": "q1", "kind": "free_text", "prompt": "?", "difficulty": "L1"}], "answer_key": {}}

    monkeypatch.setattr(quiz_generation, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(quiz_generation, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(gemini_stack_service, "generate_quiz", _fake_gen)

    async with session_maker() as session:
        qs = QuizSession(
            project_id=project_id,
            developer_id=developer_id,
            file_path="src/auth.py",
            repo_full_name="acme/rosetta",
            granularity="feature",
            feature_id=feature_id,
            status="not_started",
        )
        session.add(qs)
        await session.commit()
        sid = qs.id

    req = QuizGenerationRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GENERATION,
        session_id=str(sid),
        project_id=str(project_id),
        file_path="src/auth.py",
        repo_full_name="acme/rosetta",
        github=GitHubRef(installation_id=1),
        requested_by="u",
        granularity="feature",
        feature_id=str(feature_id),
    )
    async with session_maker() as session:
        result = await quiz_generation.process(req, PipelineContext(session=session))
        await session.commit()

    assert result.question_count == 1
    assert seen["label"] == "認証"
    assert "src/auth.py" in seen["content"]
    assert "src/token.py" in seen["content"]
    assert "Authentication" in seen["content"]


async def test_grading_feature_expands_kc_to_all_files(
    monkeypatch: pytest.MonkeyPatch, session_maker: async_sessionmaker
) -> None:
    """A feature-scope quiz reflects the score onto every file in the feature (issue 054)."""
    project_id, developer_id = uuid.uuid4(), uuid.uuid4()
    feature_id = await _seed_feature(session_maker, project_id, ["src/auth.py", "src/token.py"])
    kc_run = await _seed_kc_run(session_maker, project_id)
    sid = await _seed_feature_session(
        session_maker, project_id=project_id, developer_id=developer_id, feature_id=feature_id
    )

    async def _fake_mint(github: GitHubRef) -> str:
        return "tok"

    async def _fake_grade(payload: str) -> dict:
        return {"score": 0.9, "understood": [], "gap_concepts": []}

    monkeypatch.setattr(quiz_grading, "_mint_installation_token", _fake_mint)
    monkeypatch.setattr(quiz_grading, "GitHubGitClient", lambda access_token: _FakeClient())
    monkeypatch.setattr(gemini_stack_service, "grade_quiz", _fake_grade)

    req = QuizGradingRequest(
        job_id=str(uuid.uuid4()),
        job_type=JobType.QUIZ_GRADING,
        session_id=str(sid),
        project_id=str(project_id),
        github=GitHubRef(installation_id=1),
        requested_by="u",
    )
    async with session_maker() as session:
        await quiz_grading.process(req, PipelineContext(session=session))
        await session.commit()

    async with session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(FileKc).where(
                        FileKc.run_id == kc_run, FileKc.dev_id == developer_id, FileKc.certified_via == "quiz"
                    )
                )
            )
            .scalars()
            .all()
        )
        paths = {r.file_path for r in rows}
        assert paths == {"src/auth.py", "src/token.py"}
        assert all(r.kc == 0.9 and r.mastery == "star" for r in rows)
        # one dev row per file (no duplicates).
        n = (
            await session.execute(
                select(func.count()).select_from(FileKc).where(FileKc.run_id == kc_run, FileKc.dev_id == developer_id)
            )
        ).scalar_one()
        assert n == 2
