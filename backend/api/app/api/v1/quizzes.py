"""Quiz API (issue 034) — session CRUD + generate/grade enqueue + result delivery.

Project-scoped under ``OrgScope``; each handler additionally enforces
``quiz_session.developer_id == current_user.id`` (403 otherwise). Generation and grading run as
service pipelines (``202`` enqueue + ``GET /jobs/{id}`` polling); answers save via PATCH upsert.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col
from sqlmodel import select as sm_select

from app.api.deps import CurrentUser, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import InstallationIdDep, OptionalInstallationIdDep
from app.models.user import User
from app.schemas.job import JobEnqueuedOut
from app.schemas.quiz import (
    BaselineQuizzesOut,
    FileRefOut,
    FlagQuestionIn,
    GenerateQuizIn,
    QuizAnswerOut,
    QuizListItemOut,
    QuizListOut,
    QuizResultOut,
    QuizReviewItemOut,
    QuizSessionOut,
    RetestIn,
    RetestOut,
    SaveAnswerIn,
)
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobStatus, JobType
from shared.models import (
    AnalysisRun,
    Feature,
    FeatureFile,
    QuizAnswer,
    QuizQuestionFlag,
    QuizResult,
    QuizSession,
)
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["quizzes"])


def _clean_snippet(snippet: dict | None) -> dict | None:
    """Keep a code snippet only if it has real content; drop placeholder/empty/malformed ones to None."""
    if not isinstance(snippet, dict):
        return None
    content = snippet.get("content")
    if not isinstance(content, str) or not content.strip() or content.strip() == "...":
        return None
    return {
        "language": str(snippet.get("language") or ""),
        "path": str(snippet.get("path") or ""),
        "content": content,
    }


def _normalize_questions(questions: list) -> list[dict]:
    """Ensure each stored question has the keys the frontend ``quizQuestionSchema`` requires."""
    out: list[dict] = []
    for q in questions:
        if isinstance(q, dict):
            q = dict(q)
            q["code_snippet"] = _clean_snippet(q.get("code_snippet"))
            out.append(q)
    return out


def _answer_correct(answer_key: dict, question_id: str, value: str | None) -> bool | None:
    """Deterministically match a saved answer against the key (mirrors quiz_grading._choice_matches).

    Correctness is derived at read time from ``answer_key`` + the saved value rather than trusting the
    persisted ``quiz_answers.is_correct`` — so review (#4) and wrong-retest (#6) work for sessions
    graded before per-question correctness was stored. Returns ``None`` when the question is ungradeable.
    """
    key = answer_key.get(question_id)
    if not isinstance(key, dict):
        return None
    expected = key.get("answer")
    if expected is None:
        return None
    if value is None:
        return False
    # Multi-select may be a list or a comma-string; compare as id sets (mirror quiz_grading._choice_matches, issue 074).
    if isinstance(expected, list) or "," in str(expected) or "," in str(value):
        exp = (
            {str(e).strip() for e in expected}
            if isinstance(expected, list)
            else {p.strip() for p in str(expected).split(",") if p.strip()}
        )
        chosen = {p.strip() for p in str(value).split(",") if p.strip()}
        return chosen == exp
    return str(value).strip() == str(expected).strip()


def _labels_for(value: object, id_to_label: dict[str, str]) -> str:
    """Map a stored answer value (choice id, or comma-separated ids / list) to human labels."""
    if value is None:
        return ""
    ids = [str(v).strip() for v in value] if isinstance(value, list) else [p.strip() for p in str(value).split(",")]
    return "、".join(id_to_label.get(i, i) for i in ids if i)


def _build_review(
    questions: list, answer_key: dict, answers: list[QuizAnswer], flagged_qids: set[str]
) -> list[QuizReviewItemOut]:
    """Build per-question review rows (#4): your answer vs correct answer + correctness + flag."""
    given = {a.question_id: a for a in answers}
    review: list[QuizReviewItemOut] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id"))
        key = answer_key.get(q.get("id")) or answer_key.get(qid)
        if not isinstance(key, dict) or key.get("answer") is None:
            continue
        id_to_label = {str(c.get("id")): str(c.get("label", c.get("id"))) for c in (q.get("choices") or [])}
        ans = given.get(qid)
        # Derive correctness from the key (read-time) so it works even when is_correct was never stored.
        answered = ans is not None and (ans.value or "").strip() != ""
        is_correct = bool(_answer_correct(answer_key, qid, ans.value)) if answered else False
        review.append(
            QuizReviewItemOut(
                question_id=qid,
                prompt=str(q.get("prompt") or qid),
                your_answer=_labels_for(ans.value if answered else None, id_to_label),
                correct_answer=_labels_for(key.get("answer"), id_to_label),
                is_correct=is_correct,
                flagged=qid in flagged_qids,
            )
        )
    return review


async def _flagged_qids(db: AsyncSession, *, session_id: uuid.UUID, developer_id: uuid.UUID) -> set[str]:
    """Return the question ids this developer flagged within a session (#6)."""
    rows = (
        (
            await db.execute(
                select(col(QuizQuestionFlag.question_id)).where(
                    col(QuizQuestionFlag.session_id) == session_id,
                    col(QuizQuestionFlag.developer_id) == developer_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _owned_session(db: AsyncSession, *, session_id: uuid.UUID, project_id: uuid.UUID, user: User) -> QuizSession:
    """Load a quiz session scoped to the project + current user (404 / 403)."""
    row = (await db.execute(select(QuizSession).where(col(QuizSession.id) == session_id))).scalar_one_or_none()
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="クイズが見つかりません")
    if row.developer_id != user.id:
        raise HTTPException(status_code=403, detail="このクイズにアクセスする権限がありません")
    return row


async def _session_out(db: AsyncSession, qs: QuizSession) -> QuizSessionOut:
    answers = (await db.execute(select(QuizAnswer).where(col(QuizAnswer.session_id) == qs.id))).scalars().all()
    flagged = await _flagged_qids(db, session_id=qs.id, developer_id=qs.developer_id)
    return QuizSessionOut(
        id=str(qs.id),
        developer_id=str(qs.developer_id),
        file=FileRefOut(path=qs.file_path, repo_full_name=qs.repo_full_name),
        questions=_normalize_questions(qs.questions),
        answers=[QuizAnswerOut(question_id=a.question_id, value=a.value, saved_at=a.saved_at) for a in answers],
        status=qs.status,
        started_at=qs.started_at,
        completed_at=qs.completed_at,
        score=qs.score,
        flagged_question_ids=sorted(flagged),
        retest_mode=qs.retest_mode,
    )


@router.get("/orgs/{slug}/projects/{project_slug}/quizzes", response_model=QuizListOut, summary="受験可能なクイズ一覧")
async def list_quizzes(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> QuizListOut:
    """Return this developer's *answerable* quiz sessions for the project.

    Only ``not_started`` / ``in_progress`` are offered — ``grading`` and ``completed`` sessions have
    their answers locked (the save endpoint 409s), so listing them as "受験可能" would drop the user
    into an answering screen where every save silently fails. Completed sessions are reached via their
    result page instead (see the ``[sessionId]`` route guard).
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    rows = (
        (
            await session.execute(
                select(QuizSession).where(
                    col(QuizSession.project_id) == project.id,
                    col(QuizSession.developer_id) == current_user.id,
                    col(QuizSession.status).in_(["not_started", "in_progress"]),
                )
            )
        )
        .scalars()
        .all()
    )
    quizzes = [
        QuizListItemOut(
            session_id=str(r.id),
            file_path=r.file_path,
            repo_full_name=r.repo_full_name,
            reason="Knowledge Coverage が低いファイル",  # 029/030 由来の理由は未配線（固定文言）
            question_count=len(r.questions),
            estimated_minutes=max(1, len(r.questions) * 2),
        )
        for r in rows
    ]
    return QuizListOut(quizzes=quizzes)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/quizzes/generate",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="クイズ生成を enqueue する",
)
async def generate_quiz(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    body: GenerateQuizIn,
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Create a quiz session and enqueue ``quiz_generation`` for the target file."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    quiz = QuizSession(
        project_id=project.id,
        developer_id=current_user.id,
        file_path=body.file_path,
        repo_full_name=project.repo_full_name,
        status="not_started",
    )
    session.add(quiz)
    await session.flush()
    payload = {
        "session_id": str(quiz.id),
        "project_id": str(project.id),
        "file_path": body.file_path,
        "repo_full_name": project.repo_full_name,
        "branch": project.default_branch or "main",
        "requested_by": str(current_user.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.QUIZ_GENERATION,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/baseline-quizzes",
    response_model=BaselineQuizzesOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="機能ごとのベースライン理解度クイズを生成する（自分の受験分）",
)
async def generate_baseline_quizzes(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> BaselineQuizzesOut:
    """Create a baseline quiz session per feature for the caller and enqueue generation (issue 054).

    Opt-in / self-scoped (only the caller's sessions) to avoid mass Job fan-out. Idempotent: a
    feature that already has an open baseline session for the caller is skipped. 409 if feature
    clustering (issue 052) has not run yet.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    run = (
        await session.exec(
            sm_select(AnalysisRun)
            .where(
                col(AnalysisRun.project_id) == project.id,
                col(AnalysisRun.kind) == JobType.FEATURE_CLUSTERING.value,
                col(AnalysisRun.status) == JobStatus.COMPLETED,
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).first()
    if run is None:
        raise HTTPException(status_code=409, detail="機能クラスタリングが未実行です")

    features = (await session.exec(sm_select(Feature).where(col(Feature.run_id) == run.id))).all()
    job_ids: list[str] = []
    for feat in features:
        existing = (
            await session.exec(
                sm_select(QuizSession).where(
                    col(QuizSession.project_id) == project.id,
                    col(QuizSession.developer_id) == current_user.id,
                    col(QuizSession.feature_id) == feat.id,
                    col(QuizSession.is_baseline).is_(True),
                    col(QuizSession.status) != "completed",
                )
            )
        ).first()
        if existing is not None:
            continue  # already has an open baseline session for this feature
        rep = (
            await session.exec(
                sm_select(FeatureFile)
                .where(col(FeatureFile.feature_id) == feat.id)
                .order_by(col(FeatureFile.confidence).desc())
                .limit(1)
            )
        ).first()
        quiz = QuizSession(
            project_id=project.id,
            developer_id=current_user.id,
            file_path=rep.file_path if rep is not None else "",
            repo_full_name=project.repo_full_name,
            granularity="feature",
            feature_id=feat.id,
            is_baseline=True,
            status="not_started",
        )
        session.add(quiz)
        await session.flush()
        payload = {
            "session_id": str(quiz.id),
            "project_id": str(project.id),
            "file_path": quiz.file_path,
            "repo_full_name": project.repo_full_name,
            "branch": project.default_branch or "main",
            "requested_by": str(current_user.id),
            "github": {"installation_id": installation_id},
            "granularity": "feature",
            "feature_id": str(feat.id),
        }
        job = await enqueue_job(
            session=session,
            dispatcher=dispatcher,
            blob_client=blob,
            job_type=JobType.QUIZ_GENERATION,
            payload=payload,
            created_by=current_user.id,
            project_id=project.id,
        )
        job_ids.append(str(job.id))
    return BaselineQuizzesOut(created=len(job_ids), job_ids=job_ids)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}",
    response_model=QuizSessionOut,
    summary="クイズセッションを返す（正答は除去）",
)
async def get_quiz_session(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> QuizSessionOut:
    """Return one quiz session (questions without the answer key; answers joined)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    qs = await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    return await _session_out(session, qs)


@router.patch(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}/answers",
    response_model=QuizAnswerOut,
    summary="回答を途中保存する（upsert）",
)
async def save_quiz_answer(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    body: SaveAnswerIn,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> QuizAnswerOut:
    """Upsert one answer; mark the session ``in_progress`` (and set ``started_at`` on first save)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    qs = await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    if qs.status in ("grading", "completed"):
        # Answers must not change once grading has started / finished (issue-040).
        raise HTTPException(status_code=409, detail="採点中または採点済みのクイズは編集できません")

    now = datetime.now(UTC)
    stmt = pg_insert(QuizAnswer).values(
        id=uuid.uuid4(), session_id=session_id, question_id=body.question_id, value=body.value, saved_at=now
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_quiz_answers_session_question", set_={"value": body.value, "saved_at": now}
    )
    await session.execute(stmt)

    if qs.status == "not_started":
        qs.status = "in_progress"
        qs.started_at = now
        session.add(qs)
    await session.commit()
    return QuizAnswerOut(question_id=body.question_id, value=body.value, saved_at=now)


@router.put(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}/questions/{question_id}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="設問にフラグを設定/解除する（#6）",
)
async def flag_question(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    question_id: Annotated[str, Path(description="Question id within the session.")],
    body: FlagQuestionIn,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> Response:
    """Set (insert-if-absent) or clear the caller's flag on one question in a session (#6)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    if body.flagged:
        stmt = pg_insert(QuizQuestionFlag).values(
            developer_id=current_user.id, session_id=session_id, question_id=question_id
        )
        await session.execute(stmt.on_conflict_do_nothing(constraint="uq_quiz_question_flags_dev_session_q"))
    else:
        await session.execute(
            delete(QuizQuestionFlag).where(
                col(QuizQuestionFlag.developer_id) == current_user.id,
                col(QuizQuestionFlag.session_id) == session_id,
                col(QuizQuestionFlag.question_id) == question_id,
            )
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _retest_question_ids(
    db: AsyncSession, *, source: QuizSession, mode: str, developer_id: uuid.UUID
) -> list[str]:
    """Pick the question ids to include in a re-test (#6).

    ``flagged``: questions the caller flagged in the source session.
    ``wrong``: questions answered incorrectly on *every* graded attempt across the retest chain
    (「全回間違えた問題だけ」). The chain is the source's origin (or itself) plus all its retests.
    """
    all_qids = [str(q.get("id")) for q in source.questions if isinstance(q, dict) and q.get("id") is not None]
    if mode == "all":
        return all_qids  # 全問を再受験（同じ設問セットの新しい試行）
    if mode == "flagged":
        flagged = await _flagged_qids(db, session_id=source.id, developer_id=developer_id)
        return [qid for qid in all_qids if qid in flagged]

    # mode == "wrong": incorrect on all attempts across the chain.
    root_id = source.origin_session_id or source.id
    chain = (
        (
            await db.execute(
                select(QuizSession).where(
                    col(QuizSession.developer_id) == developer_id,
                    (col(QuizSession.id) == root_id) | (col(QuizSession.origin_session_id) == root_id),
                )
            )
        )
        .scalars()
        .all()
    )
    # Correctness is derived at read time from each session's own answer_key (not the is_correct
    # column) so sessions graded before per-question correctness was stored still work.
    key_by_session = {s.id: s.answer_key for s in chain}
    answers = (
        (await db.execute(select(QuizAnswer).where(col(QuizAnswer.session_id).in_([s.id for s in chain]))))
        .scalars()
        .all()
    )
    graded: dict[str, list[bool]] = {}
    for a in answers:
        correct = _answer_correct(key_by_session.get(a.session_id, {}), a.question_id, a.value)
        if correct is not None:
            graded.setdefault(a.question_id, []).append(correct)
    # 全回誤答: at least one graded attempt, and none of them correct.
    return [qid for qid in all_qids if graded.get(qid) and not any(graded[qid])]


@router.post(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}/retest",
    response_model=RetestOut,
    status_code=status.HTTP_201_CREATED,
    summary="フィルタ再テストを作成する（フラグのみ / 全回誤答のみ）（#6）",
)
async def create_retest(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    body: RetestIn,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> RetestOut:
    """Create a new not-started session that reuses a filtered subset of the source's questions (#6).

    Deterministic — no Gemini: questions and answer key are copied verbatim from the source, so the
    re-test measures the same items. 404 if the source is missing, 400 for bad mode / empty subset.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    source = await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    if body.mode not in ("flagged", "wrong", "all"):
        raise HTTPException(status_code=400, detail="mode は all / flagged / wrong を指定してください")

    qids = await _retest_question_ids(session, source=source, mode=body.mode, developer_id=current_user.id)
    if not qids:
        raise HTTPException(status_code=400, detail="対象の設問がありません")
    keep = set(qids)
    questions = [q for q in source.questions if isinstance(q, dict) and str(q.get("id")) in keep]
    answer_key = {qid: source.answer_key[qid] for qid in source.answer_key if str(qid) in keep}

    retest = QuizSession(
        project_id=project.id,
        developer_id=current_user.id,
        file_path=source.file_path,
        repo_full_name=source.repo_full_name,
        granularity=source.granularity,
        feature_id=source.feature_id,
        status="not_started",
        questions=questions,
        answer_key=answer_key,
        origin_session_id=source.origin_session_id or source.id,
        retest_mode=body.mode,
    )
    session.add(retest)
    await session.commit()
    return RetestOut(session_id=str(retest.id), question_count=len(questions))


@router.post(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}/submit",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="採点を enqueue する（grading へ遷移）",
)
async def submit_quiz(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    org_membership: OrgScope,
    installation_id: OptionalInstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue ``quiz_grading`` and move the session to ``grading``."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    qs = await session.get(QuizSession, session_id)
    if qs is None or qs.project_id != project.id:
        raise HTTPException(status_code=404, detail="クイズが見つかりません")
    if qs.developer_id != current_user.id:
        raise HTTPException(status_code=403, detail="このクイズにアクセスする権限がありません")
    if qs.status in ("grading", "completed"):
        # Already submitted — don't re-enqueue grading or discard a finished result (issue-040).
        raise HTTPException(status_code=409, detail="このクイズは既に提出済みです")
    qs.status = "grading"
    session.add(qs)
    payload = {
        "session_id": str(session_id),
        "project_id": str(project.id),
        "requested_by": str(current_user.id),
        # Demo users have no installation (None) → 0 sentinel; quiz_grading then grades offline.
        "github": {"installation_id": installation_id or 0},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.QUIZ_GRADING,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/quizzes/{session_id}/result",
    response_model=QuizResultOut,
    summary="採点結果を返す（未採点は 404）",
)
async def get_quiz_result(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    session_id: uuid.UUID,
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> QuizResultOut:
    """Return the graded result for a session (404 until grading completes)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    qs = await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    result = (
        await session.execute(select(QuizResult).where(col(QuizResult.session_id) == session_id))
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="まだ採点が完了していません")
    answers = (
        (await session.execute(select(QuizAnswer).where(col(QuizAnswer.session_id) == session_id))).scalars().all()
    )
    flagged = await _flagged_qids(session, session_id=session_id, developer_id=current_user.id)
    review = _build_review(qs.questions, qs.answer_key, list(answers), flagged)
    return QuizResultOut(
        session_id=str(result.session_id),
        understood=list(result.understood),
        gap_concepts=list(result.gap_concepts),
        kc_before=result.kc_before,
        kc_after=result.kc_after,
        learning_plan_id=str(result.learning_plan_id) if result.learning_plan_id else None,
        review=review,
    )
