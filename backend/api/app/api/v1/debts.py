"""Debt API — code-debt detection trigger (issue 028).

``POST .../detect-debts`` is async (issue 018 pattern): it resolves the caller's GitHub App
installation id, enqueues a ``code_debt_detection`` Job via Cloud Tasks for the project's
repository, and returns ``202`` immediately — the heavy static analysis + Gemini run in the
``service`` container off the request path. The frontend polls ``GET /jobs/{id}``.

The debt **listing / detail** delivery (``GET .../debts``) is owned by issue 031; this module
only owns the detection trigger.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentUser, OrgAdminScope, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import GitHubClientDep, InstallationIdDep
from app.models.org import OrgMember
from app.models.user import User
from app.schemas.debt import DebtItemOut, DebtListOut, DebtUpdate, RepaymentPrCreate
from app.schemas.job import JobEnqueuedOut
from app.services.credits import assert_has_credit
from app.services.debt_query import get_debt, list_debts
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobType
from shared.models import AssignedDeveloper, CodeDebt, KnowledgeDebt
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["debts"])

_CODE_STATUSES = {"open", "in_pr", "resolved", "dismissed"}
_KNOWLEDGE_STATUSES = {"open", "in_progress", "resolved"}
_AGENT_TO_KIND = {"code_debt": "code", "knowledge_debt": "knowledge"}


@router.post(
    "/orgs/{slug}/projects/{project_slug}/detect-debts",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="コード負債検知を非同期ジョブとして enqueue する",
)
async def detect_debts(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue a ``code_debt_detection`` job for the project's repository and return ``202``.

    The detection (complexity / duplication / dead code + AI-generation estimate) runs in the
    ``service`` container; method B keeps the GitHub secret off the queue (only ``installation_id``
    travels). The frontend polls ``GET /jobs/{job_id}`` for the result summary.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    payload = {
        "owner": project.repo_owner,
        "repo": project.repo_name,
        "branch": project.default_branch or "main",
        "requested_by": str(current_user.id),  # audit only
        "project_id": str(project.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.CODE_DEBT_DETECTION,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


@router.get(
    "/orgs/{slug}/projects/{project_slug}/debts",
    response_model=DebtListOut,
    summary="負債レジストリ（code + knowledge）をフィルタ/ソートして返す",
)
async def list_project_debts(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
    kind: Annotated[list[str] | None, Query()] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    debt_status: Annotated[list[str] | None, Query(alias="status")] = None,
    agent: Annotated[list[str] | None, Query()] = None,
    sort_key: Annotated[str, Query()] = "severity",
    sort_dir: Annotated[str, Query()] = "desc",
) -> DebtListOut:
    """Return the latest code + knowledge debts with filter/sort applied (``debtListSchema``)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    # ``agent`` (code_debt/knowledge_debt) is 1:1 with kind; fold it into the kind filter.
    kinds = list(kind) if kind else None
    if agent:
        agent_kinds = [_AGENT_TO_KIND[a] for a in agent if a in _AGENT_TO_KIND]
        kinds = agent_kinds if kinds is None else [k for k in kinds if k in agent_kinds]
    return await list_debts(
        session,
        project,
        kinds=kinds,
        severities=severity,
        statuses=debt_status,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )


@router.get(
    "/orgs/{slug}/projects/{project_slug}/debts/{debt_id}",
    response_model=DebtItemOut,
    summary="単一の負債を返す（assigned_developers join 込み）",
)
async def get_project_debt(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    debt_id: uuid.UUID,
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> DebtItemOut:
    """Return a single debt (code or knowledge) by id. 404 if not found in this project."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    debt = await get_debt(session, project, debt_id)
    if debt is None:
        raise HTTPException(status_code=404, detail="負債が見つかりません")
    return debt


@router.patch(
    "/orgs/{slug}/projects/{project_slug}/debts/{debt_id}",
    response_model=DebtItemOut,
    summary="負債を部分更新する（status / 担当割当）",
)
async def patch_project_debt(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    debt_id: uuid.UUID,
    body: DebtUpdate,
    org_membership: OrgScope,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> DebtItemOut:
    """Patch a debt's status and/or assigned developer (PATCH 部分更新; kind 別 status 検証)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)

    code = await session.get(CodeDebt, debt_id)
    code = code if code is not None and code.project_id == project.id else None
    kn = None
    if code is None:
        kn = await session.get(KnowledgeDebt, debt_id)
        kn = kn if kn is not None and kn.project_id == project.id else None
    if code is None and kn is None:
        raise HTTPException(status_code=404, detail="負債が見つかりません")

    kind = "code" if code is not None else "knowledge"
    if body.status is not None:
        valid = _CODE_STATUSES if kind == "code" else _KNOWLEDGE_STATUSES
        if body.status not in valid:
            raise HTTPException(status_code=422, detail=f"{kind} 負債に status={body.status} は指定できません")
        if code is not None:
            code.status = body.status
            session.add(code)
        elif kn is not None:
            kn.status = body.status
            session.add(kn)

    if body.assignee_github_handle:
        existing = (
            await session.execute(
                select(AssignedDeveloper).where(
                    col(AssignedDeveloper.debt_kind) == kind,
                    col(AssignedDeveloper.debt_id) == debt_id,
                    col(AssignedDeveloper.github_handle) == body.assignee_github_handle,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.coverage = body.assignee_coverage if body.assignee_coverage is not None else existing.coverage
            existing.certified_via = body.assignee_certified_via or existing.certified_via
            session.add(existing)
        else:
            session.add(
                AssignedDeveloper(
                    debt_kind=kind,
                    debt_id=debt_id,
                    github_handle=body.assignee_github_handle,
                    coverage=body.assignee_coverage or 0.0,
                    certified_via=body.assignee_certified_via,
                )
            )

    await session.commit()
    debt = await get_debt(session, project, debt_id)
    if debt is None:  # pragma: no cover - just updated
        raise HTTPException(status_code=404, detail="負債が見つかりません")
    return debt


@router.post(
    "/orgs/{slug}/projects/{project_slug}/debts/{debt_id}/repayment-pr",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="返済 PR 生成を非同期ジョブとして enqueue する（org 管理者）",
)
async def create_repayment_pr(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    debt_id: uuid.UUID,
    org_membership: OrgAdminScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
    body: RepaymentPrCreate | None = None,
) -> JobEnqueuedOut:
    """Enqueue a ``repayment_pr_generation`` job for a code debt (GitHub write → 202, admin only)."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    debt = await session.get(CodeDebt, debt_id)
    if debt is None or debt.project_id != project.id:
        raise HTTPException(status_code=404, detail="負債が見つかりません")
    if debt.status == "in_pr" and debt.related_pr:
        raise HTTPException(status_code=409, detail=f"既に返済 PR が作成済みです（{debt.related_pr}）")
    # 修正 PR 生成も Gemini を呼ぶため、残高 > 0 を要求する（消費はしない — issue 298）。
    # ANALYSIS_CREDITS_ENABLED 無効時・superuser はバイパス。
    await assert_has_credit(current_user)
    # PR 先（base）ブランチ。指定が無ければプロジェクトの解析対象（既定）ブランチ。
    base_branch = (body.base_branch if body and body.base_branch else project.default_branch) or "main"
    payload = {
        "debt_id": str(debt_id),
        "owner": project.repo_owner,
        "repo": project.repo_name,
        "branch": base_branch,
        "requested_by": str(current_user.id),  # audit only
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.REPAYMENT_PR_GENERATION,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)


def _issue_body(debt: CodeDebt, file_path: str, assignee_label: str | None = None) -> str:
    """Build the GitHub issue body for the 人に頼む remediation path (issue 210)."""
    lines = [
        f"## 技術負債: `{file_path}`",
        "",
        f"- 種別: {debt.type}",
        f"- 深刻度: {debt.severity}",
        f"- 推定修正工数: 約 {debt.estimated_repay_hours} 時間",
    ]
    if assignee_label:
        lines.append(f"- 担当: {assignee_label}")
    lines += [
        "",
        "### 検知根拠",
        debt.archaeology_notes or "（記録なし）",
    ]
    if debt.code_snippet:
        lines += ["", "### 該当コード", "```", debt.code_snippet.rstrip("\n"), "```"]
    lines += ["", "---", "DevDebtOps の「人に頼む」返済経路から作成されました。"]
    return "\n".join(lines)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/debts/{debt_id}/issue",
    response_model=DebtItemOut,
    summary="担当を割り当てて GitHub issue を作成する（人に頼む経路, org 管理者）",
)
async def create_debt_issue(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    debt_id: uuid.UUID,
    body: DebtUpdate,
    org_membership: OrgAdminScope,
    github: GitHubClientDep,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> DebtItemOut:
    """Assign a developer (optional) and open a GitHub issue for a code debt (GitHub write, admin only).

    「人に頼む」返済経路（issue 210）: 担当者(GitHubハンドル)を割り当ててから issue を作成し、その URL を
    ``code_debts.related_issue`` に保存する。issue 作成は軽量なので同期で行う（返済PRのような非同期ジョブは不要）。
    冪等性: 既に related_issue があれば再作成せず 409。
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    debt = await session.get(CodeDebt, debt_id)
    if debt is None or debt.project_id != project.id:
        raise HTTPException(status_code=404, detail="負債が見つかりません")
    if debt.related_issue:
        raise HTTPException(status_code=409, detail=f"既に Issue が作成済みです（{debt.related_issue}）")

    # 担当（任意）: ワークスペースのユーザーを指定。GitHub ハンドルは保持していないため、issue 本文に
    # 担当者名を記すに留める（GitHub の assignees は付与しない）。org メンバーであることを検証する。
    assignee_label: str | None = None
    if body.assignee_user_id:
        member = (
            await session.execute(
                select(OrgMember).where(
                    col(OrgMember.org_id) == org.id,
                    col(OrgMember.user_id) == body.assignee_user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=404, detail="指定された担当者が見つかりません")
        user = await session.get(User, body.assignee_user_id)
        assignee_label = (user.display_name or user.email) if user is not None else None

    title = f"[技術負債] {debt.file_path} の{debt.type}（{debt.severity}）"
    try:
        _number, issue_url = await github.create_issue(
            project.repo_owner,
            project.repo_name,
            title=title,
            body=_issue_body(debt, debt.file_path, assignee_label),
            labels=["tech-debt"],
        )
    except Exception as e:  # GitHub 失敗はそのまま 502 で返す
        raise HTTPException(status_code=502, detail="GitHub issue の作成に失敗しました") from e

    debt.related_issue = issue_url
    session.add(debt)
    await session.commit()

    result = await get_debt(session, project, debt_id)
    if result is None:  # pragma: no cover - just updated
        raise HTTPException(status_code=404, detail="負債が見つかりません")
    return result
