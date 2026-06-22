"""Build the feature-unit learn→confirm hub payload (issue 063).

Joins the 055 feature KC rollup with each feature's learning plan (``learning_plans.feature_id``)
and confirmation quiz (``quiz_sessions`` with ``granularity="feature"``) for one developer, and
derives a unit status so the frontend can show 学習 → 確認クイズ → 理解済み per feature.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.project import Project
from app.schemas.knowledge_unit import KnowledgeUnitOut
from app.services.debt_query import _latest_run_id, build_overview
from shared.enums import JobType
from shared.models import Feature, LearningPlan, QuizSession

_STAR = 0.7  # KC ≥ star → 理解済み（ADR 0003）
_BLACK_HOLE = 0.4


def _status(kc: float, has_plan: bool, quiz_status: str | None) -> str:
    if kc >= _STAR:
        return "verified"
    if quiz_status == "completed" and kc < _BLACK_HOLE:
        return "needs_review"
    if has_plan or quiz_status is not None:
        return "in_progress"
    return "unstarted"


async def build_knowledge_units(
    session: AsyncSession, project: Project, developer_id: uuid.UUID
) -> list[KnowledgeUnitOut]:
    """Return one unit per clustered feature (empty when feature clustering has not run)."""
    run_id = await _latest_run_id(session, project.id, JobType.FEATURE_CLUSTERING)
    if run_id is None:
        return []
    features = (await session.execute(select(Feature).where(col(Feature.run_id) == run_id))).scalars().all()
    if not features:
        return []

    # 055 rollup gives KC / code / file_count per feature key.
    overview = await build_overview(session, project, "", granularity="feature")
    node_by_key = {n.key: n for n in overview.features}

    units: list[KnowledgeUnitOut] = []
    for feat in features:
        node = node_by_key.get(feat.key)
        plan = (
            await session.execute(
                select(LearningPlan)
                .where(
                    col(LearningPlan.project_id) == project.id,
                    col(LearningPlan.feature_id) == feat.id,
                    col(LearningPlan.developer_id) == developer_id,
                )
                .order_by(col(LearningPlan.created_at).desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        qs = (
            await session.execute(
                select(QuizSession)
                .where(
                    col(QuizSession.project_id) == project.id,
                    col(QuizSession.feature_id) == feat.id,
                    col(QuizSession.developer_id) == developer_id,
                )
                .order_by(col(QuizSession.started_at).desc().nulls_last())
                .limit(1)
            )
        ).scalar_one_or_none()
        kc = node.knowledge_coverage if node is not None else 0.0
        units.append(
            KnowledgeUnitOut(
                feature_id=str(feat.id),
                feature_key=feat.key,
                name=feat.name,
                knowledge_coverage=kc,
                code_debt_score=node.code_debt_score if node is not None else 0.0,
                file_count=node.file_count if node is not None else 0,
                status=_status(kc, plan is not None, qs.status if qs is not None else None),
                learning_plan_id=str(plan.id) if plan is not None else None,
                quiz_session_id=str(qs.id) if qs is not None else None,
                quiz_status=qs.status if qs is not None else None,
            )
        )
    return units
