"""agent-loop pipeline (issue 036) — bind detection domains into a 5-stage narrative.

Shared ``process`` for ``code_debt_loop`` / ``knowledge_debt_loop`` (branch on ``kind``). MVP is
**read-and-narrate** (ADR 0004): it reads the latest detection run (028 ``code_debts`` / 030
``knowledge_debts``), builds the 5-stage pipeline state machine, and generates a first-person
narrative + archaeology evidence via Gemini — it does NOT re-run detection or sub-enqueue generation
(``repay``/``verify`` stay ``pending``; those are driven by 033/034 endpoints). Cross-domain
``evidence.href`` links into the Matrix registry. Idempotent by ``job_id``.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service.services import gemini_stack_service
from shared.enums import JobType, ResultStatus
from shared.models import (
    AgentActivity,
    AgentPipeline,
    AnalysisRun,
    CodeDebt,
    KnowledgeDebt,
    NarrativeEvidence,
    NarrativeStep,
)
from shared.pipelines.context import PipelineContext
from shared.schemas.agent_loop import AgentLoopRequest, AgentLoopResult

logger = logging.getLogger(__name__)

_VALID_STATUS = {"scanning", "analyzing", "creating_pr", "running_quiz", "succeeded", "failed", "pending"}
_STAGE_DEFS = {
    "code_debt": [
        ("detect", "検知", "負債スキャン"),
        ("analyze", "分析", "考古学解析"),
        ("plan", "計画", "返済計画"),
        ("repay", "返済", "返済 PR 作成"),
        ("verify", "検証", "CI 自己確認"),
    ],
    "knowledge_debt": [
        ("detect", "検知", "KC 算出"),
        ("analyze", "分析", "知識ギャップ解析"),
        ("plan", "計画", "学習計画"),
        ("repay", "返済", "クイズ生成"),
        ("verify", "検証", "再クイズ判定"),
    ],
}
_DETECTION_KIND = {"code_debt": JobType.CODE_DEBT_DETECTION, "knowledge_debt": JobType.KNOWLEDGE_DEBT_DETECTION}


def _build_stages(pipeline_id: uuid.UUID, kind: str, has_findings: bool) -> list[dict]:
    """The 5-stage state machine; detect/analyze/plan succeed when findings exist, repay/verify pending."""
    done = {"detect", "analyze", "plan"}
    stages = []
    for key, label, node_label in _STAGE_DEFS[kind]:
        status = "succeeded" if (has_findings and key in done) else "pending"
        stages.append(
            {
                "key": key,
                "label": label,
                "nodes": [{"id": f"{pipeline_id}:{key}", "label": node_label, "status": status, "retryable": False}],
            }
        )
    return stages


def _evidence_for(row: CodeDebt | KnowledgeDebt | None) -> list[dict]:
    """Archaeology evidence from the top finding, with a cross-domain href into the Matrix."""
    if row is None:
        return []
    href = f"/matrix/{row.id}"  # cross-domain link to the debt detail
    notes = getattr(row, "archaeology_notes", None) or getattr(row, "detection_notes", None)
    ev: list[dict] = [{"type": "first_commit", "label": "考古学的根拠", "detail": notes, "href": href}]
    prob = getattr(row, "ai_generation_prob", 0.0)
    if prob and prob >= 0.5:
        ev.append({"type": "ai_generated", "label": "AI 生成痕跡", "detail": f"{prob:.0%}", "href": href})
    related_adr = getattr(row, "related_adr", None)
    if related_adr:
        ev.append({"type": "adr_reference", "label": related_adr, "detail": None, "href": href})
    related_pr = getattr(row, "related_pr", None)
    if related_pr:
        ev.append({"type": "pr_review", "label": related_pr, "detail": None, "href": href})
    return ev


async def _latest_findings(session: AsyncSession, project_id: uuid.UUID, kind: str) -> list:
    run = (
        await session.execute(
            select(AnalysisRun)
            .where(col(AnalysisRun.project_id) == project_id, col(AnalysisRun.kind) == _DETECTION_KIND[kind].value)
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return []
    model = CodeDebt if kind == "code_debt" else KnowledgeDebt
    rows = (await session.execute(select(model).where(col(model.run_id) == run.id).limit(5))).scalars().all()
    return list(rows)


def _summary(kind: str, findings: list) -> str:
    parts = []
    for r in findings:
        label = r.type if kind == "code_debt" else r.reason
        parts.append(f"- {r.file_path}: {label} ({r.severity})")
    return "\n".join(parts)


async def process(request: AgentLoopRequest, ctx: PipelineContext) -> AgentLoopResult:
    """Bind the latest detection into a narrative pipeline + activity (read-and-narrate MVP)."""
    if ctx.session is None:
        raise RuntimeError("agent_loop pipeline requires a DB session in the pipeline context")
    session = ctx.session
    kind = request.kind
    job_id = uuid.UUID(request.job_id)
    project_id = uuid.UUID(request.project_id)

    # Idempotent: reuse the pipeline/activity for this job on redelivery.
    existing = (
        await session.execute(select(AgentPipeline).where(col(AgentPipeline.job_id) == job_id))
    ).scalar_one_or_none()
    if existing is not None:
        activity = (
            await session.execute(select(AgentActivity).where(col(AgentActivity.pipeline_id) == existing.id))
        ).scalar_one_or_none()
        return _result(request, activity_id=str(activity.id) if activity else "", pipeline_id=str(existing.id), steps=0)

    findings = await _latest_findings(session, project_id, kind)
    summary = _summary(kind, findings)
    try:
        narrative = await gemini_stack_service.generate_agent_narrative(kind, summary)
    except ValueError:
        narrative = {"headline": "", "steps": []}

    pipeline = AgentPipeline(
        project_id=project_id,
        kind=kind,
        status="analyzing" if findings else "pending",
        stages=[],  # set after we have the id
        job_id=job_id,
    )
    session.add(pipeline)
    await session.flush()
    pipeline.stages = _build_stages(pipeline.id, kind, bool(findings))
    session.add(pipeline)

    headline_raw = narrative.get("headline")
    headline = (
        str(headline_raw)
        if headline_raw
        else (
            "コード負債を検知し返済を計画しました" if kind == "code_debt" else "知識ギャップを検知し学習を計画しました"
        )
    )
    activity = AgentActivity(project_id=project_id, kind=kind, headline=headline, pipeline_id=pipeline.id)
    session.add(activity)
    await session.flush()

    steps_raw = narrative.get("steps")
    steps_list = steps_raw if isinstance(steps_raw, list) else []
    if not steps_list:
        steps_list = [{"status": "succeeded", "message": headline}]
    top = findings[0] if findings else None
    step_count = 0
    for order, s in enumerate(steps_list):
        sd = s if isinstance(s, dict) else {}
        raw_status = sd.get("status")
        status = str(raw_status) if raw_status in _VALID_STATUS else "succeeded"
        step = NarrativeStep(activity_id=activity.id, order=order, status=status, message=str(sd.get("message") or ""))
        session.add(step)
        await session.flush()
        # Attach evidence to the analyze step (order 1) when we have a finding.
        if order == 1 and top is not None:
            for e in _evidence_for(top):
                session.add(
                    NarrativeEvidence(
                        step_id=step.id, type=e["type"], label=e["label"], detail=e["detail"], href=e["href"]
                    )
                )
        step_count += 1

    await session.commit()
    logger.info("agent_loop(%s): activity %s, %s steps", kind, activity.id, step_count)
    return _result(request, activity_id=str(activity.id), pipeline_id=str(pipeline.id), steps=step_count)


def _result(request: AgentLoopRequest, *, activity_id: str, pipeline_id: str, steps: int) -> AgentLoopResult:
    return AgentLoopResult(
        job_id=request.job_id,
        job_type=request.job_type,
        status=ResultStatus.COMPLETED,
        kind=request.kind,
        activity_id=activity_id,
        pipeline_id=pipeline_id,
        step_count=steps,
        trace=[f"{request.kind} loop bound {steps} narrative steps"],
    )
