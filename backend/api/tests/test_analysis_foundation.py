"""issue 026: analysis_runs / repo_files の FK・一意制約・pgvector 拡張の検証。

api 所有の DB に対し、共有テーブルが create_all で生成され（models/__init__ の import 順効果）、
FK と (run_id, path) 一意制約が効くこと、CREATE EXTENSION vector が冪等であることを確認する。
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import db as app_db
from app.models.project import Project
from shared.enums import JobStatus
from shared.models import AnalysisRun, RepoFile


async def test_analysis_run_project_fk_enforced() -> None:
    """存在しない project_id の AnalysisRun は FK 違反になる。"""
    async with app_db.async_session_maker() as session:
        session.add(
            AnalysisRun(project_id=uuid.uuid4(), commit_sha="deadbeef", kind="code_debt_detection"),
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_repo_file_unique_and_chain(authenticated_client: AsyncClient) -> None:
    """user→org→project→run を実シードし、repo_files の (run_id, path) 一意制約が効く。"""
    me = (await authenticated_client.get("/api/v1/users/me")).json()
    user_id = uuid.UUID(me["id"])
    orgs = (await authenticated_client.get("/api/v1/orgs")).json()
    org_id = uuid.UUID(orgs[0]["id"])

    async with app_db.async_session_maker() as session:
        project = Project(
            org_id=org_id,
            name="Foundation",
            slug="foundation",
            repo_owner="acme",
            repo_name="rosetta",
            repo_full_name="acme/rosetta",
            created_by=user_id,
        )
        session.add(project)
        await session.commit()
        run = AnalysisRun(
            project_id=project.id,
            commit_sha="abc123",
            kind="code_debt_detection",
            status=JobStatus.COMPLETED,
        )
        session.add(run)
        await session.commit()
        run_id = run.id
        session.add(RepoFile(run_id=run_id, path="src/a.py", language="Python", loc=42))
        await session.commit()

    # 同一 (run_id, path) は一意制約違反。
    async with app_db.async_session_maker() as session:
        session.add(RepoFile(run_id=run_id, path="src/a.py"))
        with pytest.raises(IntegrityError):
            await session.commit()

    # 別パスは挿入できる。
    async with app_db.async_session_maker() as session:
        session.add(RepoFile(run_id=run_id, path="src/b.py"))
        await session.commit()


async def test_vector_extension_idempotent() -> None:
    """CREATE EXTENSION IF NOT EXISTS vector が冪等（pgvector イメージ前提、2 回適用で落ちない）。"""
    async with app_db.async_session_maker() as session:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.commit()
