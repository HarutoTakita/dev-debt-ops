"""quiz-generation pipeline (issue 034).

Fetches the target file, asks Gemini for an L1–L5 quiz + answer key, and fills the
``quiz_sessions`` row created by the api. ``shared.worker.run_task`` owns the Job lifecycle.
Idempotent: if the session already has questions, regeneration is skipped.
"""

import logging
import uuid

from sqlalchemy import select
from sqlmodel import col

from service import config
from service.services import gemini_stack_service
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGenerationRequest, QuizGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def process(request: QuizGenerationRequest, ctx: PipelineContext) -> QuizGenerationResult:
    """Generate quiz questions for the session's file and persist them."""
    if ctx.session is None:
        raise RuntimeError("quiz_generation pipeline requires a DB session in the pipeline context")
    session = ctx.session

    quiz = (
        await session.execute(select(QuizSession).where(col(QuizSession.id) == uuid.UUID(request.session_id)))
    ).scalar_one_or_none()
    if quiz is None:
        return QuizGenerationResult(
            job_id=request.job_id,
            job_type=JobType.QUIZ_GENERATION,
            status=ResultStatus.COMPLETED,
            session_id=request.session_id,
            question_count=0,
            agent_trace=["session not found"],
        )
    if quiz.questions:  # already generated → idempotent skip
        return QuizGenerationResult(
            job_id=request.job_id,
            job_type=JobType.QUIZ_GENERATION,
            status=ResultStatus.COMPLETED,
            session_id=request.session_id,
            question_count=len(quiz.questions),
            agent_trace=["already generated"],
        )

    owner, _, repo = request.repo_full_name.partition("/")
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        fc = await client.get_file_content(owner, repo, request.file_path, request.branch)
        generated = await gemini_stack_service.generate_quiz(request.file_path, fc.content or "")
    finally:
        await client.aclose()

    quiz.questions = generated["questions"]
    quiz.answer_key = generated["answer_key"]
    session.add(quiz)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)

    logger.info("quiz_generation: %s questions for session %s", len(quiz.questions), request.session_id)
    return QuizGenerationResult(
        job_id=request.job_id,
        job_type=JobType.QUIZ_GENERATION,
        status=ResultStatus.COMPLETED,
        session_id=request.session_id,
        question_count=len(quiz.questions),
        agent_trace=[f"generated {len(quiz.questions)} questions"],
    )
