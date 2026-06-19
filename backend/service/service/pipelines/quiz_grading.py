"""quiz-grading pipeline (issue 034).

Semantically grades a submitted quiz (answers + answer key) with Gemini, extracts understood /
gap concepts, computes a provisional ``kc_before``/``kc_after`` (KC 本算出は issue 029), writes
``quiz_results`` and completes the session. Idempotent: a completed session is not re-graded.

``certified_via="quiz"`` の file_kc 反映は issue 029 が所有する（本 issue は配線位置のみ — run スコープの
file_kc 更新メカニズムは 029 側。ここでは結果の永続化に留め、フック箇所をログで明示する）。
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col

from service import config
from service.services import gemini_stack_service
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import QuizAnswer, QuizResult, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGradingRequest, QuizGradingResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _provisional_kc_after(kc_before: float, score: float) -> float:
    """Provisional KC after a quiz: passing nudges KC toward 1.0 (real formula is issue 029)."""
    return round(min(1.0, kc_before + (1.0 - kc_before) * score), 4)


async def process(request: QuizGradingRequest, ctx: PipelineContext) -> QuizGradingResult:
    """Grade the session and persist quiz_results; mark the session completed."""
    if ctx.session is None:
        raise RuntimeError("quiz_grading pipeline requires a DB session in the pipeline context")
    session = ctx.session
    sid = uuid.UUID(request.session_id)

    quiz = (await session.execute(select(QuizSession).where(col(QuizSession.id) == sid))).scalar_one_or_none()
    if quiz is None:
        return _result(request, score=0.0, kc_before=0.0, kc_after=0.0, trace=["session not found"])
    if quiz.status == "completed":  # idempotent: do not re-grade (free_text grading is non-deterministic)
        return _result(
            request, score=quiz.score or 0.0, kc_before=0.0, kc_after=quiz.score or 0.0, trace=["already completed"]
        )

    answers = (await session.execute(select(QuizAnswer).where(col(QuizAnswer.session_id) == sid))).scalars().all()
    payload = json.dumps(
        {
            "questions": quiz.questions,
            "answer_key": quiz.answer_key,
            "answers": [{"question_id": a.question_id, "value": a.value} for a in answers],
        },
        ensure_ascii=False,
    )
    # File context for grading (best-effort; method B token).
    owner, _, repo = quiz.repo_full_name.partition("/")
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        if owner and repo:
            fc = await client.get_file_content(owner, repo, quiz.file_path, "main")
            payload = f"{payload}\n\n=== {quiz.file_path} ===\n{(fc.content or '')[:4000]}"
    finally:
        await client.aclose()

    graded = await gemini_stack_service.grade_quiz(payload)
    score = graded["score"]
    kc_before = quiz.source_kc if quiz.source_kc is not None else 0.0
    kc_after = _provisional_kc_after(kc_before, score)

    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "session_id": sid,
        "understood": graded["understood"],
        "gap_concepts": graded["gap_concepts"],
        "kc_before": kc_before,
        "kc_after": kc_after,
        "learning_plan_id": None,
    }
    stmt = pg_insert(QuizResult).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_quiz_results_session",
        set_={k: values[k] for k in ("understood", "gap_concepts", "kc_before", "kc_after")},
    )
    await session.execute(stmt)

    quiz.status = "completed"
    quiz.score = score
    quiz.completed_at = now
    session.add(quiz)
    await session.commit()

    # KC 反映フック（issue 029 所有）: certified_via="quiz" の file_kc 更新はここで呼ぶ配線位置。
    logger.info("quiz_grading: session %s scored %.2f (kc %.2f→%.2f)", request.session_id, score, kc_before, kc_after)
    return _result(request, score=score, kc_before=kc_before, kc_after=kc_after, trace=["graded"])


def _result(
    request: QuizGradingRequest, *, score: float, kc_before: float, kc_after: float, trace: list[str]
) -> QuizGradingResult:
    return QuizGradingResult(
        job_id=request.job_id,
        job_type=JobType.QUIZ_GRADING,
        status=ResultStatus.COMPLETED,
        session_id=request.session_id,
        score=score,
        kc_before=kc_before,
        kc_after=kc_after,
        agent_trace=trace,
    )
