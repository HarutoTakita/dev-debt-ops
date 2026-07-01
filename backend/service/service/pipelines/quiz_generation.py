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
from service.services import quiz_authoring
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import Feature, FeatureFile, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGenerationRequest, QuizGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_MAX_FEATURE_FILES = 5  # representative files fed to Gemini for a feature-scope quiz
_MAX_FEATURE_FILE_CHARS = 3000


async def _feature_content(session, client, request: QuizGenerationRequest) -> tuple[str, str]:
    """Return ``(label, combined_content)`` for a feature-scope quiz (issue 054).

    Combines the feature description with its top representative files' contents so Gemini can
    write feature-spanning comprehension questions rather than single-file ones.
    """
    feature_id = uuid.UUID(str(request.feature_id))
    feat = (await session.execute(select(Feature).where(col(Feature.id) == feature_id))).scalar_one_or_none()
    files = (
        (
            await session.execute(
                select(FeatureFile)
                .where(col(FeatureFile.feature_id) == feature_id)
                .order_by(col(FeatureFile.confidence).desc())
                .limit(_MAX_FEATURE_FILES)
            )
        )
        .scalars()
        .all()
    )
    owner, _, repo = request.repo_full_name.partition("/")
    blocks: list[str] = []
    for ff in files:
        fc = await client.get_file_content(owner, repo, ff.file_path, request.branch)
        blocks.append(f"=== {ff.file_path} ===\n{(fc.content or '')[:_MAX_FEATURE_FILE_CHARS]}")
    label = feat.name if feat is not None else (request.feature_id or "feature")
    header = f"Feature: {label}\n{feat.description if feat is not None else ''}".strip()
    return label, f"{header}\n\n{chr(10).join(blocks)}"


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
    token = await _mint_installation_token(request.github)  # required for the agentic quiz's clone
    # Reuse the job's shared read-caching client for file fetches when present (agentic backbone),
    # else mint our own. The clone inside generate_quiz_agentic still uses ``token``.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=token)
    try:
        # Agentic authoring (issue 217 PR3): the agent follows dependencies via Serena for deeper
        # questions; the same token clones the repo. Falls back to the direct path.
        if request.granularity == "feature" and request.feature_id:
            label, content = await _feature_content(session, client, request)
            generated = await quiz_authoring.generate_quiz_agentic(
                owner, repo, request.branch, label, content, token=token
            )
        else:
            fc = await client.get_file_content(owner, repo, request.file_path, request.branch)
            generated = await quiz_authoring.generate_quiz_agentic(
                owner, repo, request.branch, request.file_path, fc.content or "", token=token
            )
    finally:
        if shared_client is None:
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
