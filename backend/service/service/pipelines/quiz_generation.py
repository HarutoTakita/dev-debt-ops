"""quiz-generation pipeline (issue 034).

Fetches the target file, asks Gemini for an L1–L5 quiz + answer key, and fills the
``quiz_sessions`` row created by the api. ``shared.worker.run_task`` owns the Job lifecycle.
Idempotent: if the session already has questions, regeneration is skipped.

``process`` = ``prepare_inputs`` (read-only, on the session) → ``generate`` (Gemini, session-free) →
``persist`` (flush-only, on the session). The stages are exposed so the baseline fan-out
(``baseline_generation``) can run ``generate`` concurrently across features while keeping DB work serial.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import code_analysis, quiz_authoring
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


def _clip(body: str) -> str:
    """Slice a file body to the cap, appending a truncation marker so the model knows it was cut (074-E)."""
    if len(body) > _MAX_FEATURE_FILE_CHARS:
        return body[:_MAX_FEATURE_FILE_CHARS] + "\n... (truncated)"
    return body


async def _feature_content(
    session: AsyncSession, client: GitHubGitClient, *, feature_id: str, repo_full_name: str, branch: str
) -> tuple[str, str, bool]:
    """Return ``(label, combined_content, has_code)`` for a feature-scope quiz (issue 054).

    Combines the feature description with its top representative files' contents so Gemini can
    write feature-spanning comprehension questions rather than single-file ones. ``has_code`` is
    ``True`` iff at least one non-empty file body was assembled (issue 074-D: without real code the
    model would fabricate the mandatory ``code_snippet``).
    """
    fid = uuid.UUID(str(feature_id))
    feat = (await session.execute(select(Feature).where(col(Feature.id) == fid))).scalar_one_or_none()
    files = (
        (
            await session.execute(
                select(FeatureFile)
                .where(col(FeatureFile.feature_id) == fid)
                .order_by(col(FeatureFile.confidence).desc())
                .limit(_MAX_FEATURE_FILES)
            )
        )
        .scalars()
        .all()
    )
    owner, _, repo = repo_full_name.partition("/")
    blocks: list[str] = []
    has_code = False
    for ff in files:
        fc = await client.get_file_content(owner, repo, ff.file_path, branch)
        body = fc.content or ""
        if body.strip():
            has_code = True
        # 実装が始まる行から抜粋（docstring/import 主体のファイルで素材が自然言語だけになるのを防ぐ）。
        blocks.append(f"=== {ff.file_path} ===\n{_clip(code_analysis.implementation_excerpt(body))}")
    label = feat.name if feat is not None else (str(feature_id) or "feature")
    header = f"Feature: {label}\n{feat.description if feat is not None else ''}".strip()
    return label, f"{header}\n\n{chr(10).join(blocks)}", has_code


def _coherent_quiz(questions: object, answer_key: object) -> tuple[list, dict]:
    """Keep only questions that have a valid answer_key entry; prune orphan keys (issue 074-B).

    An ungradeable question (no answer_key entry, or entry without ``answer``) must not be served —
    otherwise grading later inflates the score (dropped from the denominator) or marks it wrong.
    """
    if not isinstance(questions, list) or not isinstance(answer_key, dict):
        return [], {}
    kept: list = []
    keys: dict = {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = q.get("id")
        entry = answer_key.get(qid)
        if isinstance(entry, dict) and entry.get("answer") is not None:
            kept.append(q)
            keys[qid] = entry
    return kept, keys


def _skip_result(request: QuizGenerationRequest, reason: str) -> QuizGenerationResult:
    """A COMPLETED result with no questions (baseline's per-feature loop treats this as a normal skip)."""
    return QuizGenerationResult(
        job_id=request.job_id,
        job_type=JobType.QUIZ_GENERATION,
        status=ResultStatus.COMPLETED,
        session_id=request.session_id,
        question_count=0,
        agent_trace=[reason],
    )


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


@dataclass
class QuizInputs:
    """Read-only inputs for quiz generation, gathered before the Gemini step.

    ``skip_reason`` is set when there is no usable code (empty file / no feature content) — the
    ``generate`` step then returns ``None`` and ``persist`` records a skip instead of fabricating
    a hallucinated quiz (issue 074-D).
    """

    owner: str
    repo: str
    branch: str
    label: str
    content: str
    token: str
    skip_reason: str | None = None


async def prepare_inputs(
    session: AsyncSession,
    ctx: PipelineContext,
    *,
    granularity: str,
    feature_id: str | None,
    file_path: str,
    repo_full_name: str,
    branch: str,
    github: GitHubRef,
) -> QuizInputs:
    """Read the quiz's source content (feature files or a single file) + mint the clone token. No writes."""
    owner, _, repo = repo_full_name.partition("/")
    token = await _mint_installation_token(github)  # required for the agentic quiz's clone
    # Reuse the job's shared read-caching client for file fetches when present (agentic backbone),
    # else mint our own. The clone inside generate_quiz_agentic still uses ``token``.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=token)
    try:
        if granularity == "feature" and feature_id:
            label, content, has_code = await _feature_content(
                session, client, feature_id=feature_id, repo_full_name=repo_full_name, branch=branch
            )
            if not has_code:
                # 実コードが無い（FeatureFile 0 件 / 取得内容が空）→ 生成すると code_snippet を捏造した
                # 幻覚設問になる。生成せずスキップ（issue 074-D）。
                return QuizInputs(
                    owner,
                    repo,
                    branch,
                    label,
                    "",
                    token,
                    skip_reason="insufficient context: no code content; quiz generation skipped",
                )
            return QuizInputs(owner, repo, branch, label, content, token)
        fc = await client.get_file_content(owner, repo, file_path, branch)
        body = fc.content or ""
        if not body.strip():
            return QuizInputs(
                owner,
                repo,
                branch,
                file_path,
                "",
                token,
                skip_reason="insufficient context: empty file; quiz generation skipped",
            )
        return QuizInputs(owner, repo, branch, file_path, body, token)
    finally:
        if shared_client is None:
            await client.aclose()


async def generate(inputs: QuizInputs) -> dict | None:
    """Agentic quiz authoring (no DB access → safe to run concurrently). ``None`` when the input is skipped."""
    if inputs.skip_reason is not None:
        return None
    return await quiz_authoring.generate_quiz_agentic(
        inputs.owner, inputs.repo, inputs.branch, inputs.label, inputs.content, token=inputs.token
    )


async def persist(session: AsyncSession, inputs: QuizInputs, generated: dict | None, *, quiz: QuizSession) -> int:
    """Persist the generated questions onto ``quiz`` (flush only). Returns the kept-question count."""
    if generated is None:
        logger.info("quiz_generation: skipping %s — %s", inputs.label, inputs.skip_reason)
        return 0
    # 有効な answer_key を持つ設問だけを残す（採点不能な設問を出さない, issue 074-B）。
    quiz.questions, quiz.answer_key = _coherent_quiz(generated["questions"], generated["answer_key"])
    session.add(quiz)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
    logger.info("quiz_generation: %s questions for session %s", len(quiz.questions), quiz.id)
    return len(quiz.questions)


async def process(request: QuizGenerationRequest, ctx: PipelineContext) -> QuizGenerationResult:
    """Generate quiz questions for the session's file and persist them: prepare → generate → persist."""
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

    inputs = await prepare_inputs(
        session,
        ctx,
        granularity=request.granularity,
        feature_id=request.feature_id,
        file_path=request.file_path,
        repo_full_name=request.repo_full_name,
        branch=request.branch,
        github=request.github,
    )
    generated = await generate(inputs)
    count = await persist(session, inputs, generated, quiz=quiz)
    if generated is None and inputs.skip_reason is not None:
        return _skip_result(request, inputs.skip_reason)
    return QuizGenerationResult(
        job_id=request.job_id,
        job_type=JobType.QUIZ_GENERATION,
        status=ResultStatus.COMPLETED,
        session_id=request.session_id,
        question_count=count,
        agent_trace=[f"generated {count} questions"],
    )
