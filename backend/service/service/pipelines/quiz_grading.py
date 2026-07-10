"""quiz-grading pipeline (issue 034 + 053).

Deterministically grades a submitted quiz (choice-only — free-text was removed in 0.0.5) by matching
answers against the answer key, extracts understood / gap concepts (the correct / incorrect question
prompts), writes ``quiz_results``, completes the session, and reflects the score into ``file_kc`` as
``certified_via="quiz"`` (issue 053, ADR 0005). Idempotent: a completed session is not re-graded.

Grading is **rule-based (no LLM, no GitHub fetch)** so Gemini is only ever called by the repository
analysis and the repayment-PR flows (issue 298 — bounds Gemini cost to credit-gated actions).

KC reflection is **blame-independent and uncapped** (a passing quiz can reach ``star``), unlike
authorship which is capped at 0.6 — this lets solo authors and non-coding PMs be measured.
"""

import logging
import posixpath
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service.pipelines.kc_analysis import mastery_from_kc
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, FeatureFile, FileKc, QuizAnswer, QuizResult, QuizSession
from shared.pipelines.context import PipelineContext
from shared.schemas.quiz import QuizGradingRequest, QuizGradingResult

logger = logging.getLogger(__name__)


def _choice_matches(expected: object, given: object) -> bool:
    """Match a stored answer against a saved value; shape-agnostic for multi-select (issue 074).

    Multi-select answers may be persisted as a Python list (some seeds) OR a comma-separated string
    (the model / issue 040). Compare as a set of choice ids in both cases so id order / spacing don't
    mark a correct answer wrong. Single-choice → trimmed string equality.
    """
    if given is None:
        return False
    if isinstance(expected, list) or "," in str(expected) or "," in str(given):
        exp = (
            {str(e).strip() for e in expected}
            if isinstance(expected, list)
            else {p.strip() for p in str(expected).split(",") if p.strip()}
        )
        chosen = {p.strip() for p in str(given).split(",") if p.strip()}
        return chosen == exp
    return str(given).strip() == str(expected).strip()


def _grade_offline(questions: list, answer_key: dict, answers: list[dict]) -> dict:
    """Deterministically grade a choice-only quiz with no GitHub/LLM (the sole grader — issue 298).

    Returns ``score`` (fraction correct), ``understood`` / ``gap_concepts`` (the prompts of the
    correct / incorrect questions), and ``correct_by_qid`` ({question_id: bool}) so the grader can
    persist per-question correctness onto ``quiz_answers`` (#4 誤答チェック / #6 全回誤答再テスト).
    """
    given = {a["question_id"]: a.get("value") for a in answers}
    total = 0
    correct = 0
    # understood/gap_concepts are {id, label} dicts (concept shape the result UI renders).
    understood: list[dict] = []
    gap: list[dict] = []
    correct_by_qid: dict[str, bool] = {}
    for q in questions:
        if not isinstance(q, dict):
            continue  # 本物の設問でない（壊れた要素）はスキップ
        qid = q.get("id")
        total += 1
        concept = {"id": str(qid), "label": q.get("prompt") or str(qid)}
        key = answer_key.get(qid)
        expected = key.get("answer") if isinstance(key, dict) else None
        # answer_key が無い / answer が None の設問は採点不能。分母から落とすとスコアが水増しされる
        # （例: 5 問中 1 問無キー・4 問正解 → 4/4=1.0）ため、不正解として計上する（issue 074-B）。
        is_correct = _choice_matches(expected, given.get(qid)) if expected is not None else False
        correct_by_qid[str(qid)] = is_correct
        if is_correct:
            correct += 1
            understood.append(concept)
        else:
            gap.append(concept)
    return {
        "score": (correct / total) if total else 0.0,
        "understood": understood,
        "gap_concepts": gap,
        "correct_by_qid": correct_by_qid,
    }


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
    answer_dicts = [{"question_id": a.question_id, "value": a.value} for a in answers]

    # Quizzes are choice-only (free-text removed in 0.0.5), so grade deterministically — no GitHub
    # fetch, no Gemini (issue 298). ``request.github`` is retained on the schema but unused here.
    graded = _grade_offline(quiz.questions, quiz.answer_key, answer_dicts)
    score = graded["score"]

    # Persist per-question correctness onto the saved answers (#4 誤答チェック / #6 全回誤答再テスト).
    correct_by_qid: dict[str, bool] = graded["correct_by_qid"]
    for a in answers:
        if a.question_id in correct_by_qid:
            a.is_correct = correct_by_qid[a.question_id]
            session.add(a)

    # Reflect the score into file_kc (certified_via="quiz", uncapped — issue 053 / ADR 0005).
    # A feature-scope session (issue 054) expands uniformly to every file in the feature.
    project_uuid = uuid.UUID(request.project_id)
    if quiz.granularity == "feature" and quiz.feature_id is not None:
        feature_files = (
            (await session.execute(select(FeatureFile).where(col(FeatureFile.feature_id) == quiz.feature_id)))
            .scalars()
            .all()
        )
        reflected = None
        for ff in feature_files:
            r = await _reflect_quiz_kc(
                session, project_id=project_uuid, file_path=ff.file_path, developer_id=quiz.developer_id, score=score
            )
            if r is not None and reflected is None:
                reflected = r  # representative before/after for the result summary
    else:
        reflected = await _reflect_quiz_kc(
            session, project_id=project_uuid, file_path=quiz.file_path, developer_id=quiz.developer_id, score=score
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
