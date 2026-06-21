"""Quiz API (issue 034) — session CRUD + generate/grade enqueue + result delivery.

Project-scoped under ``OrgScope``; each handler additionally enforces
``quiz_session.developer_id == current_user.id`` (403 otherwise). Generation and grading run as
service pipelines (``202`` enqueue + ``GET /jobs/{id}`` polling); answers save via PATCH upsert.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col
from sqlmodel import select as sm_select

from app.api.deps import CurrentUser, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import InstallationIdDep
from app.models.user import User
from app.schemas.job import JobEnqueuedOut
from app.schemas.quiz import (
    BaselineQuizzesOut,
    FileRefOut,
    GenerateQuizIn,
    QuizAnswerOut,
    QuizListItemOut,
    QuizListOut,
    QuizResultOut,
    QuizSessionOut,
    SaveAnswerIn,
)
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobStatus, JobType
from shared.models import AnalysisRun, Feature, FeatureFile, QuizAnswer, QuizResult, QuizSession
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["quizzes"])


def _normalize_questions(questions: list) -> list[dict]:
    """Ensure each stored question has the keys the frontend ``quizQuestionSchema`` requires."""
    out: list[dict] = []
    for q in questions:
        if isinstance(q, dict):
            q = dict(q)
            q.setdefault("code_snippet", None)
            out.append(q)
    return out


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
    )


@router.get("/orgs/{slug}/projects/{project_slug}/quizzes", response_model=QuizListOut, summary="受験可能なクイズ一覧")
async def list_quizzes(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> QuizListOut:
    """Return this developer's not-yet-completed quiz sessions for the project."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    rows = (
        (
            await session.execute(
                select(QuizSession).where(
                    col(QuizSession.project_id) == project.id,
                    col(QuizSession.developer_id) == current_user.id,
                    col(QuizSession.status) != "completed",
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
    installation_id: InstallationIdDep,
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
        "github": {"installation_id": installation_id},
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
    await _owned_session(session, session_id=session_id, project_id=project.id, user=current_user)
    result = (
        await session.execute(select(QuizResult).where(col(QuizResult.session_id) == session_id))
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="まだ採点が完了していません")
    return QuizResultOut(
        session_id=str(result.session_id),
        understood=list(result.understood),
        gap_concepts=list(result.gap_concepts),
        kc_before=result.kc_before,
        kc_after=result.kc_after,
        learning_plan_id=str(result.learning_plan_id) if result.learning_plan_id else None,
    )
