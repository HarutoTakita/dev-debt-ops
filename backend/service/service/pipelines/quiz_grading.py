"""quiz-grading pipeline (issue 034 + 053).

Semantically grades a submitted quiz (answers + answer key) with Gemini, extracts understood /
gap concepts, writes ``quiz_results``, completes the session, and reflects the score into
``file_kc`` as ``certified_via="quiz"`` (issue 053, ADR 0005). Idempotent: a completed session is
not re-graded.

KC reflection is **blame-independent and uncapped** (a passing quiz can reach ``star``), unlike
authorship which is capped at 0.6 — this lets solo authors and non-coding PMs be measured.
"""

import json
import logging
import posixpath
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.pipelines.kc_analysis import mastery_from_kc
from service.services import gemini_stack_service
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, FileKc, QuizAnswer, QuizResult, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGradingRequest, QuizGradingResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _upsert_kc_row(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    file_path: str,
    dev_id: uuid.UUID | None,
    kc: float,
    certified_via: str | None,
) -> None:
    """Upsert one ``file_kc`` row (dev row when ``dev_id`` set, else the aggregate row)."""
    now = datetime.now(UTC)
    module = posixpath.dirname(file_path) or "(root)"
    mastery = mastery_from_kc(kc, has_contact=True)
    values = {
        "id": uuid.uuid4(),
        "run_id": run_id,
        "file_path": file_path,
        "module": module,
        "dev_id": dev_id,
        "github_handle": None,
        "kc": kc,
        "mastery": mastery,
        "certified_via": certified_via,
        "computed_at": now,
    }
    update = {"module": module, "kc": kc, "mastery": mastery, "certified_via": certified_via, "computed_at": now}
    stmt = pg_insert(FileKc).values(**values)
    if dev_id is not None:
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path", "dev_id"], index_where=text("dev_id IS NOT NULL"), set_=update
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "file_path"],
            index_where=text("dev_id IS NULL AND github_handle IS NULL"),
            set_=update,
        )
    await session.execute(stmt)


async def _reflect_quiz_kc(
    session: AsyncSession, *, project_id: uuid.UUID, file_path: str, developer_id: uuid.UUID, score: float
) -> tuple[float, float] | None:
    """Reflect a quiz score into ``file_kc`` (``certified_via="quiz"``); return ``(kc_before, kc_after)``.

    Uncapped and blame-independent (ADR 0005): ``kc = max(existing, score)``. Anchored to the
    project's latest COMPLETED ``kc_analysis`` run. Returns ``None`` when no such run exists (no
    anchor to attach ``file_kc`` to). The aggregate row is re-derived from all dev rows.
    """
    run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project_id,
                col(AnalysisRun.kind) == JobType.KC_ANALYSIS.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    existing = (
        await session.execute(
            select(FileKc).where(
                col(FileKc.run_id) == run.id,
                col(FileKc.file_path) == file_path,
                col(FileKc.dev_id) == developer_id,
            )
        )
    ).scalar_one_or_none()
    prev_kc = existing.kc if existing is not None else 0.0
    new_kc = max(prev_kc, score)  # never lower an earned KC (idempotent under re-grade)
    certified = "quiz" if (existing is None or score >= prev_kc) else (existing.certified_via or "quiz")
    await _upsert_kc_row(
        session, run_id=run.id, file_path=file_path, dev_id=developer_id, kc=new_kc, certified_via=certified
    )

    # Re-derive the aggregate row (dev_id NULL / handle NULL) as the max over all dev/handle rows.
    dev_rows = (
        (
            await session.execute(
                select(FileKc).where(
                    col(FileKc.run_id) == run.id,
                    col(FileKc.file_path) == file_path,
                    text("NOT (dev_id IS NULL AND github_handle IS NULL)"),
                )
            )
        )
        .scalars()
        .all()
    )
    agg_kc = max((r.kc for r in dev_rows), default=new_kc)
    await _upsert_kc_row(session, run_id=run.id, file_path=file_path, dev_id=None, kc=agg_kc, certified_via=None)
    return prev_kc, new_kc


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
        # Echo the persisted KC delta rather than fabricating one from the score (issue-042).
        prior = (
            await session.execute(select(QuizResult).where(col(QuizResult.session_id) == sid))
        ).scalar_one_or_none()
        return _result(
            request,
            score=quiz.score or 0.0,
            kc_before=prior.kc_before if prior else 0.0,
            kc_after=prior.kc_after if prior else (quiz.score or 0.0),
            trace=["already completed"],
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

    # Reflect the score into file_kc (certified_via="quiz", uncapped — issue 053 / ADR 0005).
    reflected = await _reflect_quiz_kc(
        session,
        project_id=uuid.UUID(request.project_id),
        file_path=quiz.file_path,
        developer_id=quiz.developer_id,
        score=score,
    )
    if reflected is not None:
        kc_before, kc_after = reflected
    else:
        # No KC run to anchor to — fall back to best-effort values (no file_kc written).
        kc_before = quiz.source_kc if quiz.source_kc is not None else 0.0
        kc_after = score

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
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)

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
