"""Live job-progress reporting for long multi-step pipelines (issue 069).

The agentic-analysis job runs many sub-steps (Base Analysis Agent + deterministic backbone +
learning/quiz generation) under a SINGLE ``Job`` whose ``result_data`` / status are committed once
(atomicity, issue-042). That means the frontend's ``GET /jobs/{id}`` poll can't see internal progress.

``ProgressReporter`` writes a granular progress snapshot to ``jobs.progress`` in its OWN short-lived
transaction (a fresh session from ``async_session_maker``), independent of the pipeline's flush-only
session. So progress becomes visible *during* the run without touching the terminal result commit.
Updates are best-effort: a failed progress write never aborts the pipeline.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import update
from sqlmodel import col

from service.db import async_session_maker
from shared.models import Job

logger = logging.getLogger(__name__)

# Ordered sub-steps of the agentic-analysis job: (key, label, group). ``key`` matches the backbone
# step names; ``group`` maps each sub-step to one of the cockpit's 4 display blocks (ids match the
# frontend STAGE_GROUPS): g_explore(リポジトリ探索) / g_technical(技術負債の検知) /
# g_knowledge(理解負債の整理) / g_repay(クイズと学習の生成).
AGENTIC_STEPS: list[tuple[str, str, str]] = [
    ("base_analysis", "リポジトリ探索", "g_explore"),
    ("feature_clustering", "機能クラスタリング", "g_repay"),
    ("code_debt_detection", "コード負債の検知", "g_technical"),
    ("kc_analysis", "理解度の計測", "g_knowledge"),
    ("knowledge_debt_detection", "理解負債の検知", "g_knowledge"),
    ("stack_analysis", "技術スタックの検出", "g_technical"),
    ("baseline", "学習プラン・クイズの生成", "g_repay"),
]


class ProgressReporter:
    """Tracks ordered sub-steps and flushes a snapshot to ``jobs.progress`` on each change.

    Snapshot shape (read by the frontend cockpit)::

        {"steps": [{"key", "label", "group", "status": pending|running|completed|failed, "done"?, "total"?}, ...],
         "completed": <int>, "total": <int>}
    """

    def __init__(self, job_id: str, steps: list[tuple[str, str, str]]) -> None:
        # Tolerate a non-UUID id (e.g. unit-test fixtures): progress just becomes a no-op then.
        try:
            self._job_pk: uuid.UUID | None = uuid.UUID(str(job_id))
        except ValueError:
            self._job_pk = None
        self._steps: list[dict[str, Any]] = [
            {"key": k, "label": label, "group": group, "status": "pending"} for k, label, group in steps
        ]
        self._total = len(self._steps)

    def _snapshot(self) -> dict[str, Any]:
        completed = sum(1 for s in self._steps if s["status"] == "completed")
        return {"steps": self._steps, "completed": completed, "total": self._total}

    def _patch(self, key: str, status: str | None, **extra: Any) -> None:
        for s in self._steps:
            if s["key"] == key:
                if status is not None:
                    s["status"] = status
                s.update(extra)
                return

    async def _flush(self) -> None:
        if self._job_pk is None:
            return
        try:
            async with async_session_maker() as session:
                await session.execute(update(Job).where(col(Job.id) == self._job_pk).values(progress=self._snapshot()))
                await session.commit()
        except Exception:  # progress is best-effort — never fail the pipeline on a progress write
            logger.warning("progress update failed (non-fatal)", exc_info=True)

    async def start(self, key: str, **extra: Any) -> None:
        """Mark a step ``running`` and flush."""
        self._patch(key, "running", **extra)
        await self._flush()

    async def complete(self, key: str, **extra: Any) -> None:
        """Mark a step ``completed`` and flush."""
        self._patch(key, "completed", **extra)
        await self._flush()

    async def fail(self, key: str, **extra: Any) -> None:
        """Mark a step ``failed`` and flush (the pipeline itself continues — backbone steps are best-effort)."""
        self._patch(key, "failed", **extra)
        await self._flush()

    async def update(self, key: str, **extra: Any) -> None:
        """Update a running step's extra fields (e.g. ``done`` / ``total`` for the per-feature baseline) and flush."""
        self._patch(key, None, **extra)
        await self._flush()
