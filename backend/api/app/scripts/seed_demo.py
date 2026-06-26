"""Guest-demo seed script (issue 069): populate a sample workspace for the demo user.

Seeds a coherent, hand-curated dataset so a GitHub-less guest (the shared ``is_demo`` user from
``app.services.demo.ensure_demo_user``) lands on fully-populated screens telling the
"knowledge-debt-first" story: an Overview scatter, a debt registry (code + knowledge), a Knowledge
Galaxy, clustered features / knowledge units, an unanswered quiz to take, and a learning plan to work.

Idempotency
-----------
Every seeded row uses a **deterministic** id derived from ``uuid.uuid5(_NS, key)`` (the org / project
override their ``uuid7_pk()`` default with an explicit uuid5). Before inserting, the script checks the
row by id (or by the table's natural key), so running it repeatedly never creates duplicates. The demo
user from ``ensure_demo_user`` is already idempotent.

CLI
---
``python -m app.scripts.seed_demo``         seed (idempotent).
``python -m app.scripts.seed_demo reset``    delete the demo org's seeded analysis rows, then re-seed.

The DB must already be migrated (``alembic upgrade head``); this script never creates tables. Run it
from the ``api`` workspace member, e.g.::

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/app \
        uv run --directory api python -m app.scripts.seed_demo
"""

import argparse
import asyncio
import posixpath
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as app_db
from app.models.org import Org, OrgMember, OrgRole
from app.models.project import Project
from app.services.demo import ensure_demo_user
from shared.enums import JobStatus, JobType
from shared.models import (
    AnalysisRun,
    AssignedDeveloper,
    CodeDebt,
    DebtTrendPoint,
    Dependency,
    Feature,
    FeatureFile,
    FileKc,
    KnowledgeDebt,
    LearningPlan,
    LearningResource,
    LearningStep,
    QuizSession,
    RepoFile,
    TechStack,
)

# Stable namespace for all deterministic ids in this script. A fixed random uuid (never reused
# elsewhere) so uuid5(_NS, key) is reproducible across runs and isolated from other seeders.
_NS = uuid.UUID("0de0b6b3-7c1e-4f8a-9d2e-069000000069")

# Org / Project identity.
DEMO_ORG_SLUG = "demo"
DEMO_ORG_NAME = "お試しデモ"
DEMO_PROJECT_SLUG = "sample-shop"
DEMO_PROJECT_NAME = "sample project"
DEMO_REPO_OWNER = "devdebtops"
DEMO_REPO_NAME = "sample-shop"
DEMO_REPO_FULL_NAME = "devdebtops/sample-shop"
DEMO_DEFAULT_BRANCH = "main"

# The "現在" snapshot all latest-run screens read. A fixed commit so re-runs reuse the same runs.
_HEAD_COMMIT = "0691a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9"

# One analysis run per kind that the read endpoints look up as the "latest COMPLETED run".
_RUN_KINDS = (
    JobType.CODE_DEBT_DETECTION,
    JobType.KC_ANALYSIS,
    JobType.KNOWLEDGE_DEBT_DETECTION,
    JobType.FEATURE_CLUSTERING,
)

# Sample repository files (path → (language, loc, kc, code_debt_score)). KC drives the Overview
# scatter / Galaxy file universe; code_debt_score is the static-quality (vertical) axis. The mix
# spreads points across the two-axis matrix so every quadrant is represented.
_FILES: list[tuple[str, str, int, float, float]] = [
    ("src/checkout/payment.py", "Python", 412, 0.18, 0.82),  # P0: low KC + high code debt (hotspot)
    ("src/checkout/cart.py", "Python", 233, 0.34, 0.55),  # P1
    ("src/auth/session.py", "Python", 188, 0.27, 0.41),  # P1: low KC (knowledge hotspot)
    ("src/auth/oauth.py", "Python", 145, 0.62, 0.30),  # P2
    ("src/catalog/search.ts", "TypeScript", 320, 0.21, 0.71),  # P0
    ("src/catalog/product.ts", "TypeScript", 176, 0.74, 0.22),  # P3: well-understood, clean
    ("src/ui/checkout-form.svelte", "Svelte", 98, 0.81, 0.12),  # P3
    ("src/lib/db.py", "Python", 64, 0.55, 0.18),  # P3
]

# Feature clusters (key, name, description, [member file paths]).
_FEATURES: list[tuple[str, str, str, list[str]]] = [
    (
        "checkout",
        "決済・カート",
        "カート操作から決済確定までの中核フロー。最も理解負債が集中するホットスポット。",
        ["src/checkout/payment.py", "src/checkout/cart.py", "src/ui/checkout-form.svelte"],
    ),
    (
        "auth",
        "認証",
        "ログイン・セッション・OAuth 連携。セッション管理に理解の空白が残る。",
        ["src/auth/session.py", "src/auth/oauth.py"],
    ),
    (
        "catalog",
        "商品カタログ",
        "商品検索と一覧表示。検索ロジックにコード負債が溜まっている。",
        ["src/catalog/search.ts", "src/catalog/product.ts", "src/lib/db.py"],
    ),
]

# Intra-repo import edges (wormholes) for the galaxy.
_DEPENDENCIES: list[tuple[str, str]] = [
    ("src/checkout/payment.py", "src/checkout/cart.py"),
    ("src/checkout/cart.py", "src/lib/db.py"),
    ("src/checkout/payment.py", "src/auth/session.py"),
    ("src/catalog/search.ts", "src/catalog/product.ts"),
    ("src/auth/oauth.py", "src/auth/session.py"),
]

# Code-debt findings (file_path, type, severity, score, ai_prob, repay_hours, notes).
_CODE_DEBTS: list[tuple[str, str, str, float, float, float, str]] = [
    ("src/checkout/payment.py", "complexity", "critical", 0.82, 0.71, 6.0, "循環的複雑度 31 / 分岐の入れ子 6 段"),
    ("src/catalog/search.ts", "duplicate", "high", 0.71, 0.44, 3.5, "検索フィルタ構築の重複クラスタ 4 箇所"),
    ("src/checkout/cart.py", "complexity", "medium", 0.55, 0.33, 2.0, "在庫引当ロジックの分岐過多（複雑度 18）"),
    ("src/auth/session.py", "dead", "medium", 0.41, 0.12, 1.5, "未到達のレガシー cookie 検証パス"),
    ("src/lib/db.py", "other", "low", 0.18, 0.05, 0.5, "型ヒント欠落 / 例外の握り潰し 1 箇所"),
]

# Knowledge-debt findings (file_path, reason, severity, score, kc, ai_prob, repay_hours, notes).
_KNOWLEDGE_DEBTS: list[tuple[str, str, str, float, float, float, float, str]] = [
    (
        "src/checkout/payment.py",
        "author_left",
        "critical",
        0.82,
        0.18,
        0.71,
        6.0,
        "主要著者が退職済み・レビュー記録なし。決済の中核なのに誰も把握していない。",
    ),
    (
        "src/catalog/search.ts",
        "ai_generated",
        "high",
        0.71,
        0.21,
        0.62,
        3.0,
        "AI 生成痕跡が強く、レビューを通過したが理解者がいない。",
    ),
    (
        "src/auth/session.py",
        "no_review",
        "high",
        0.59,
        0.27,
        0.20,
        2.5,
        "セッション失効ロジックがレビューなしでマージされている。",
    ),
]

# Realistic-looking dummy source per file, shown on the code-quality detail page
# (CodeDebt / KnowledgeDebt.code_snippet → matrix/[debtId] の file-viewer)。デモ用ダミー。
_DEMO_SNIPPETS: dict[str, str] = {
    "src/checkout/payment.py": (
        "def confirm_payment(order, user, *, retries=3):\n"
        "    if order.total > 0:\n"
        "        if user.is_active:\n"
        "            if reserve_stock(order):\n"
        "                if charge(order.total, user.card):\n"
        "                    if not mark_paid(order):\n"
        "                        rollback_charge(order)  # 6 段ネスト / 循環的複雑度 31\n"
        "                        return False\n"
        "                else:\n"
        "                    release_stock(order)\n"
        "    return True\n"
    ),
    "src/catalog/search.ts": (
        "export function buildFilters(q: Query): Filter[] {\n"
        "  const f: Filter[] = [];\n"
        "  if (q.category) f.push({ field: 'category', op: 'eq', value: q.category });\n"
        "  if (q.minPrice) f.push({ field: 'price', op: 'gte', value: q.minPrice });\n"
        "  if (q.maxPrice) f.push({ field: 'price', op: 'lte', value: q.maxPrice });\n"
        "  if (q.brand) f.push({ field: 'brand', op: 'eq', value: q.brand });\n"
        "  return f; // ほぼ同一の組み立てが 4 箇所に重複（duplicate cluster）\n"
        "}\n"
    ),
    "src/checkout/cart.py": (
        "def allocate_inventory(cart):\n"
        "    for item in cart.items:\n"
        "        if item.qty <= 0:\n"
        "            continue\n"
        "        if item.sku in RESERVED and not backorder_allowed(item):\n"
        "            raise OutOfStock(item.sku)  # 分岐過多（複雑度 18）\n"
        "        reserve(item)\n"
    ),
    "src/auth/session.py": (
        "def validate_session(token):\n"
        "    claims = decode(token)\n"
        "    return claims if not claims.expired else None\n"
        "\n"
        "def _legacy_cookie_check(req):  # どこからも呼ばれない未到達パス（dead）\n"
        "    return req.cookies.get('sid_v1')\n"
    ),
    "src/lib/db.py": (
        "def fetch_one(query, params):\n"
        "    try:\n"
        "        return conn.execute(query, params).first()\n"
        "    except Exception:\n"
        "        pass  # 例外の握り潰し / 戻り値の型ヒント欠落\n"
    ),
}
_DEFAULT_SNIPPET = "# 該当コード断片（デモ用ダミー）"


# Assigned developers per debt (debt natural key → list of (handle, coverage, certified_via)).
_ASSIGNEES: dict[tuple[str, str], list[tuple[str, float, str | None]]] = {
    ("knowledge", "src/checkout/payment.py|author_left"): [("alice-dev", 0.18, "authorship")],
    ("knowledge", "src/catalog/search.ts|ai_generated"): [("bob-reviewer", 0.21, "review")],
    ("code", "src/checkout/payment.py|complexity"): [("alice-dev", 0.18, "authorship")],
}

# Weekly trend points (label → (code_debt_score, knowledge_coverage)). Earlier weeks are worse, the
# latest week shows knowledge coverage climbing — the "返済が進んでいる" narrative.
_TREND: list[tuple[str, float, float]] = [
    ("2026-W22", 0.61, 0.31),
    ("2026-W23", 0.58, 0.36),
    ("2026-W24", 0.54, 0.43),
    ("2026-W25", 0.49, 0.49),
]

# Tech stack (languages + categories) for the stack screen.
_STACK_LANGUAGES = [
    {"name": "Python", "confidence": "high"},
    {"name": "TypeScript", "confidence": "high"},
    {"name": "Svelte", "confidence": "medium"},
]
_STACK_CATEGORIES = {
    "frameworks": [{"name": "FastAPI", "confidence": "high"}, {"name": "SvelteKit", "confidence": "high"}],
    "databases": [{"name": "PostgreSQL", "confidence": "high"}],
    "auth": [{"name": "OAuth 2.0", "confidence": "medium"}],
    "container": [{"name": "Docker", "confidence": "high"}],
    "infra": [{"name": "Google Cloud Run", "confidence": "medium"}],
    "cicd": [{"name": "GitHub Actions", "confidence": "high"}],
    "monitoring": [],
    "testing": [{"name": "pytest", "confidence": "medium"}, {"name": "Vitest", "confidence": "medium"}],
    "other": [],
}

# An unanswered quiz for the lowest-KC checkout file (status not_started → appears in 受験可能 list).
_QUIZ_FILE = "src/checkout/payment.py"
_QUIZ_QUESTIONS = [
    {
        "id": "q1",
        "kind": "multiple_choice",
        "prompt": "payment.py の決済確定処理で、在庫引当が失敗したときに最初に行うべき処理はどれ？",
        "code_snippet": {
            "language": "python",
            "path": _QUIZ_FILE,
            "content": (
                "def confirm_payment(order):\n    reserve_stock(order)\n    charge(order.total)\n    mark_paid(order)"
            ),
        },
        "choices": [
            {"id": "a", "label": "課金をロールバックしてから例外を送出する"},
            {"id": "b", "label": "そのまま mark_paid を呼ぶ"},
            {"id": "c", "label": "在庫を無視して続行する"},
            {"id": "d", "label": "リトライを無限ループで回す"},
        ],
        "difficulty": "L3",
    },
    {
        "id": "q2",
        "kind": "multiple_select",
        "prompt": "この決済フローで冪等性を担保するために必要な要素をすべて選べ。",
        "code_snippet": None,
        "choices": [
            {"id": "a", "label": "冪等キー（idempotency key）"},
            {"id": "b", "label": "重複課金の検出"},
            {"id": "c", "label": "ランダムな遅延"},
            {"id": "d", "label": "決済状態の永続化"},
        ],
        "difficulty": "L4",
    },
]
_QUIZ_ANSWER_KEY = {
    "q1": {"answer": "a", "rubric": "失敗時は副作用を巻き戻すのが正解。"},
    "q2": {"answer": ["a", "b", "d"], "rubric": "冪等キー・重複検出・状態永続化が必須。"},
}

# Learning plan (gap concepts + ordered steps → resources). Team assets先頭の閉ループを表現する。
_PLAN_GAP_CONCEPTS = ["決済の冪等性", "在庫引当のトランザクション境界", "セッション失効の設計"]
# (resource key, origin, section, kind, title, summary, tech, url, minutes, priority)
_PLAN_RESOURCES: list[tuple[str, str, str, str, str, str, str, str | None, int, str]] = [
    (
        "adr-checkout",
        "team",
        "code",
        "adr",
        "ADR: 決済フローの冪等性設計",
        "なぜ冪等キーを導入したか、在庫引当と課金の順序の根拠を読む。",
        "",
        None,
        15,
        "required",
    ),
    (
        "pr-stock",
        "team",
        "code",
        "pr_comment",
        "PR #142 レビューコメント: 在庫引当の競合",
        "在庫引当のトランザクション境界を巡る議論。理解の空白を埋める一次情報。",
        "",
        None,
        10,
        "recommended",
    ),
    (
        "fastapi-deps",
        "external",
        "stack",
        "docs",
        "FastAPI 公式: Dependencies",
        "DI の依存解決順序を学び、セッション/認可の組み立てを理解する。",
        "FastAPI",
        "https://fastapi.tiangolo.com/tutorial/dependencies/",
        20,
        "supplementary",
    ),
]


def _u(*parts: object) -> uuid.UUID:
    """Return a deterministic uuid5 from ``_NS`` and the given key parts.

    Args:
        *parts: Key components joined with ``|`` to form the uuid5 name.

    Returns:
        A stable ``uuid.UUID`` reproducible across runs for the same parts.
    """
    return uuid.uuid5(_NS, "|".join(str(p) for p in parts))


def _run_id(kind: JobType) -> uuid.UUID:
    """Return the deterministic AnalysisRun id for the demo project's latest run of ``kind``."""
    return _u("run", DEMO_PROJECT_SLUG, kind.value, _HEAD_COMMIT)


async def _get(session: SAAsyncSession, model: type, row_id: uuid.UUID) -> object | None:
    """Return the row of ``model`` with primary key ``row_id``, or ``None`` if absent."""
    return await session.get(model, row_id)


async def _resolve_demo_user_id() -> uuid.UUID:
    """Resolve (creating if needed) the shared demo user's id on a plain SQLAlchemy session.

    ``ensure_demo_user`` issues a ``select(User)`` whose ``oauth_accounts`` joined-eager-load requires
    ``.unique()`` under the SQLModel ``AsyncSession``; the plain SQLAlchemy session it was written for
    handles that transparently. Resolving the id here keeps the rest of the seed on the SQLModel
    session without tripping that requirement.

    Returns:
        The demo user's ``uuid.UUID`` id.
    """
    async with app_db.sa_async_session_maker() as sa_session:
        user = await ensure_demo_user(sa_session)
        return user.id


async def _ensure_org_and_project(session: AsyncSession, user_id: uuid.UUID) -> tuple[Org, Project]:
    """Create (idempotently) the demo org, the demo user's MEMBER membership, and the demo project.

    The membership role is ``MEMBER`` (not owner/admin) so admin-gated mutations stay blocked for the
    guest. All three rows use explicit deterministic uuid5 ids so re-runs reuse them.

    Args:
        session: Open async session.
        user_id: The shared demo user's id (from ``ensure_demo_user``).

    Returns:
        The ``(Org, Project)`` pair, existing or freshly created.
    """
    org_id = _u("org", DEMO_ORG_SLUG)
    org = await _get(session, Org, org_id)
    if org is None:
        org = Org(
            id=org_id,
            name=DEMO_ORG_NAME,
            slug=DEMO_ORG_SLUG,
            is_personal=False,
            created_by=user_id,
        )
        session.add(org)

    member_id = _u("org_member", DEMO_ORG_SLUG, user_id)
    if await _get(session, OrgMember, member_id) is None:
        session.add(OrgMember(id=member_id, user_id=user_id, org_id=org_id, role=OrgRole.MEMBER))

    project_id = _u("project", DEMO_ORG_SLUG, DEMO_PROJECT_SLUG)
    project = await _get(session, Project, project_id)
    if project is None:
        project = Project(
            id=project_id,
            org_id=org_id,
            name=DEMO_PROJECT_NAME,
            slug=DEMO_PROJECT_SLUG,
            repo_owner=DEMO_REPO_OWNER,
            repo_name=DEMO_REPO_NAME,
            repo_full_name=DEMO_REPO_FULL_NAME,
            default_branch=DEMO_DEFAULT_BRANCH,
            repo_private=False,
            github_repo_id=None,
            created_by=user_id,
        )
        session.add(project)

    await session.commit()
    # Re-fetch so callers get attached, refreshed instances.
    org = await _get(session, Org, org_id)
    project = await _get(session, Project, project_id)
    if not isinstance(org, Org) or not isinstance(project, Project):  # pragma: no cover - just inserted/loaded
        raise RuntimeError("demo org/project not found after upsert")
    return org, project


async def _ensure_runs(session: AsyncSession, project: Project) -> None:
    """Create one COMPLETED AnalysisRun per analysis kind for the demo project (idempotent)."""
    created_at = datetime.now(UTC)
    for kind in _RUN_KINDS:
        run_id = _run_id(kind)
        if await _get(session, AnalysisRun, run_id) is None:
            session.add(
                AnalysisRun(
                    id=run_id,
                    project_id=project.id,
                    commit_sha=_HEAD_COMMIT,
                    branch=DEMO_DEFAULT_BRANCH,
                    kind=kind.value,
                    status=JobStatus.COMPLETED,
                    created_at=created_at,
                )
            )
    await session.commit()


async def _ensure_repo_files(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Seed RepoFile rows for the KC run (the analysed file universe), keyed deterministically."""
    for path, language, loc, _kc, _score in _FILES:
        row_id = _u("repo_file", run_id, path)
        if await _get(session, RepoFile, row_id) is None:
            session.add(RepoFile(id=row_id, run_id=run_id, path=path, language=language, loc=loc))
    await session.commit()


def _mastery_of(kc: float) -> str:
    """Map an aggregate KC into a galaxy mastery tier (mirrors galaxy_query thresholds)."""
    if kc >= 0.7:
        return "star"
    if kc >= 0.4:
        return "dim_star"
    if kc > 0.0:
        return "black_hole"
    return "unexplored"


async def _ensure_file_kc(session: AsyncSession, run_id: uuid.UUID, dev_id: uuid.UUID) -> None:
    """Seed per-file KC rows: one aggregate row (file universe) + one dev row per file.

    The Overview reads aggregate rows (``dev_id IS NULL AND github_handle IS NULL``); the Galaxy
    overlays the developer's dev rows (``dev_id`` = demo user) on that universe.
    """
    now = datetime.now(UTC)
    for path, _language, _loc, kc, _score in _FILES:
        module = posixpath.dirname(path) or "(root)"
        mastery = _mastery_of(kc)
        agg_id = _u("file_kc_agg", run_id, path)
        if await _get(session, FileKc, agg_id) is None:
            session.add(
                FileKc(
                    id=agg_id,
                    run_id=run_id,
                    file_path=path,
                    module=module,
                    dev_id=None,
                    kc=kc,
                    mastery=mastery,
                    computed_at=now,
                )
            )
        dev_kc_id = _u("file_kc_dev", run_id, path, dev_id)
        if await _get(session, FileKc, dev_kc_id) is None:
            session.add(
                FileKc(
                    id=dev_kc_id,
                    run_id=run_id,
                    file_path=path,
                    module=module,
                    dev_id=dev_id,
                    kc=kc,
                    mastery=mastery,
                    certified_via="authorship",
                    computed_at=now,
                )
            )
    await session.commit()


async def _ensure_dependencies(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Seed intra-repo import edges (wormholes) for the KC run (idempotent)."""
    for from_path, to_path in _DEPENDENCIES:
        row_id = _u("dependency", run_id, from_path, to_path)
        if await _get(session, Dependency, row_id) is None:
            session.add(
                Dependency(
                    id=row_id, run_id=run_id, from_path=from_path, to_path=to_path, computed_at=datetime.now(UTC)
                )
            )
    await session.commit()


async def _ensure_features(session: AsyncSession, project: Project, run_id: uuid.UUID) -> None:
    """Seed clustered Feature + FeatureFile rows for the feature-clustering run (idempotent)."""
    for key, name, description, paths in _FEATURES:
        feature_id = _u("feature", run_id, key)
        if await _get(session, Feature, feature_id) is None:
            session.add(
                Feature(
                    id=feature_id,
                    project_id=project.id,
                    run_id=run_id,
                    key=key,
                    name=name,
                    description=description,
                    source="ai",
                )
            )
        for path in paths:
            ff_id = _u("feature_file", run_id, key, path)
            if await _get(session, FeatureFile, ff_id) is None:
                session.add(FeatureFile(id=ff_id, run_id=run_id, feature_id=feature_id, file_path=path, confidence=0.9))
    await session.commit()


async def _ensure_code_debts(session: AsyncSession, project: Project, run_id: uuid.UUID) -> None:
    """Seed CodeDebt findings spread across the two-axis matrix (idempotent)."""
    now = datetime.now(UTC)
    kc_by_path = {path: kc for path, _l, _loc, kc, _s in _FILES}
    for file_path, dtype, severity, score, ai_prob, repay, notes in _CODE_DEBTS:
        row_id = _u("code_debt", run_id, file_path, dtype)
        if await _get(session, CodeDebt, row_id) is None:
            session.add(
                CodeDebt(
                    id=row_id,
                    project_id=project.id,
                    run_id=run_id,
                    file_path=file_path,
                    type=dtype,
                    severity=severity,
                    status="open",
                    detected_at=now,
                    archaeology_notes=notes,
                    code_snippet=_DEMO_SNIPPETS.get(file_path, _DEFAULT_SNIPPET),
                    code_debt_score=score,
                    knowledge_coverage=kc_by_path.get(file_path, 0.0),
                    ai_generation_prob=ai_prob,
                    estimated_repay_hours=repay,
                    metrics={"cyclomatic_complexity": int(score * 40)},
                    created_at=now,
                )
            )
    await session.commit()


async def _ensure_knowledge_debts(session: AsyncSession, project: Project, run_id: uuid.UUID) -> None:
    """Seed KnowledgeDebt findings (the hero signal) for the knowledge-debt run (idempotent)."""
    now = datetime.now(UTC)
    for file_path, reason, severity, score, kc, ai_prob, repay, notes in _KNOWLEDGE_DEBTS:
        row_id = _u("knowledge_debt", run_id, file_path, reason)
        if await _get(session, KnowledgeDebt, row_id) is None:
            session.add(
                KnowledgeDebt(
                    id=row_id,
                    project_id=project.id,
                    run_id=run_id,
                    file_path=file_path,
                    repo=DEMO_REPO_NAME,
                    reason=reason,
                    severity=severity,
                    status="open",
                    detected_at=now,
                    code_snippet=_DEMO_SNIPPETS.get(file_path, _DEFAULT_SNIPPET),
                    code_debt_score=score,
                    knowledge_coverage=kc,
                    ai_generation_prob=ai_prob,
                    estimated_repay_hours=repay,
                    detection_notes=notes,
                    metrics={"author_active": False},
                    created_at=now,
                )
            )
    await session.commit()


async def _ensure_assignees(session: AsyncSession) -> None:
    """Seed AssignedDeveloper rows attached to the seeded debts (idempotent).

    Debt ids are recomputed from the same deterministic keys used when the debts were inserted, so
    the assignment's ``debt_id`` resolves to the right CodeDebt / KnowledgeDebt.
    """
    code_run = _run_id(JobType.CODE_DEBT_DETECTION)
    kn_run = _run_id(JobType.KNOWLEDGE_DEBT_DETECTION)
    for (kind, natural_key), assignees in _ASSIGNEES.items():
        file_path, discriminator = natural_key.split("|", 1)
        if kind == "code":
            debt_id = _u("code_debt", code_run, file_path, discriminator)
        else:
            debt_id = _u("knowledge_debt", kn_run, file_path, discriminator)
        for handle, coverage, certified_via in assignees:
            row_id = _u("assigned_developer", kind, debt_id, handle)
            if await _get(session, AssignedDeveloper, row_id) is None:
                session.add(
                    AssignedDeveloper(
                        id=row_id,
                        debt_kind=kind,
                        debt_id=debt_id,
                        github_handle=handle,
                        coverage=coverage,
                        certified_via=certified_via,
                    )
                )
    await session.commit()


async def _ensure_trend(session: AsyncSession, project: Project) -> None:
    """Seed weekly DebtTrendPoint rows (the 地層グラフ) for the demo project (idempotent).

    Natural key is ``(project_id, week)``; the deterministic id keeps re-runs stable. ``created_at``
    is set so the Overview's newest-first ordering matches the chronological week labels.
    """
    base = datetime.now(UTC) - timedelta(days=7 * len(_TREND))
    for i, (week, code_score, kc) in enumerate(_TREND):
        row_id = _u("trend", project.id, week)
        if await _get(session, DebtTrendPoint, row_id) is None:
            session.add(
                DebtTrendPoint(
                    id=row_id,
                    project_id=project.id,
                    week=week,
                    code_debt_score=code_score,
                    knowledge_coverage=kc,
                    created_at=base + timedelta(days=7 * i),
                )
            )
    await session.commit()


async def _ensure_tech_stack(session: AsyncSession) -> None:
    """Seed the cached TechStack row for the demo repo (idempotent; natural key (owner, repo))."""
    row_id = _u("tech_stack", DEMO_REPO_OWNER, DEMO_REPO_NAME)
    if await _get(session, TechStack, row_id) is None:
        session.add(
            TechStack(
                id=row_id,
                owner=DEMO_REPO_OWNER,
                repo=DEMO_REPO_NAME,
                analyzed_at=datetime.now(UTC),
                languages=_STACK_LANGUAGES,
                categories=_STACK_CATEGORIES,
            )
        )
    await session.commit()


async def _ensure_quiz(session: AsyncSession, project: Project, dev_id: uuid.UUID) -> None:
    """Seed one UNANSWERED quiz session for the lowest-KC checkout file (idempotent).

    Left in ``not_started`` so it appears in the 受験可能 list and the guest can take it end-to-end.
    """
    row_id = _u("quiz_session", project.id, dev_id, _QUIZ_FILE)
    if await _get(session, QuizSession, row_id) is None:
        session.add(
            QuizSession(
                id=row_id,
                project_id=project.id,
                developer_id=dev_id,
                file_path=_QUIZ_FILE,
                repo_full_name=DEMO_REPO_FULL_NAME,
                granularity="file",
                status="not_started",
                questions=_QUIZ_QUESTIONS,
                answer_key=_QUIZ_ANSWER_KEY,
                source_kc=0.18,
            )
        )
    await session.commit()


async def _ensure_learning_plan(session: AsyncSession, project: Project, dev_id: uuid.UUID) -> None:
    """Seed a LearningPlan with resources + ordered steps for the checkout feature (idempotent).

    Team assets are inserted before external ones so the plan reads "チーム資産が上段" — the
    knowledge-debt repayment loop's payoff.
    """
    checkout_feature_id = _u("feature", _run_id(JobType.FEATURE_CLUSTERING), "checkout")
    plan_id = _u("learning_plan", project.id, dev_id, "checkout")

    # Resources first (steps FK them).
    resource_ids: dict[str, uuid.UUID] = {}
    for key, origin, section, kind, title, summary, tech, url, minutes, priority in _PLAN_RESOURCES:
        res_id = _u("learning_resource", project.id, key)
        resource_ids[key] = res_id
        if await _get(session, LearningResource, res_id) is None:
            session.add(
                LearningResource(
                    id=res_id,
                    project_id=project.id,
                    origin=origin,
                    section=section,
                    kind=kind,
                    title=title,
                    summary=summary,
                    tech=tech,
                    source_ref=None,
                    url=url,
                    estimated_minutes=minutes,
                    priority=priority,
                )
            )

    if await _get(session, LearningPlan, plan_id) is None:
        total = sum(r[8] for r in _PLAN_RESOURCES)
        session.add(
            LearningPlan(
                id=plan_id,
                project_id=project.id,
                developer_id=dev_id,
                feature_id=checkout_feature_id,
                gap_concepts=_PLAN_GAP_CONCEPTS,
                estimated_total_minutes=total,
            )
        )

    for order, (key, *_rest) in enumerate(_PLAN_RESOURCES):
        step_id = _u("learning_step", plan_id, order)
        if await _get(session, LearningStep, step_id) is None:
            session.add(
                LearningStep(
                    id=step_id,
                    plan_id=plan_id,
                    order=order,
                    completed=False,
                    resource_id=resource_ids[key],
                )
            )
    await session.commit()


async def seed(session: AsyncSession) -> Project:
    """Seed the full demo workspace (idempotent). Returns the demo project.

    Orchestrates every ``_ensure_*`` helper in dependency order: user → org/project → runs → files,
    KC, dependencies, features → debts + assignees → trend, stack, quiz, learning plan.

    Args:
        session: Open async session.

    Returns:
        The demo ``Project`` row.
    """
    user_id = await _resolve_demo_user_id()
    _, project = await _ensure_org_and_project(session, user_id)
    await _ensure_runs(session, project)

    kc_run = _run_id(JobType.KC_ANALYSIS)
    code_run = _run_id(JobType.CODE_DEBT_DETECTION)
    kn_run = _run_id(JobType.KNOWLEDGE_DEBT_DETECTION)
    fc_run = _run_id(JobType.FEATURE_CLUSTERING)

    await _ensure_repo_files(session, kc_run)
    await _ensure_file_kc(session, kc_run, user_id)
    await _ensure_dependencies(session, kc_run)
    await _ensure_features(session, project, fc_run)
    await _ensure_code_debts(session, project, code_run)
    await _ensure_knowledge_debts(session, project, kn_run)
    await _ensure_assignees(session)
    await _ensure_trend(session, project)
    await _ensure_tech_stack(session)
    await _ensure_quiz(session, project, user_id)
    await _ensure_learning_plan(session, project, user_id)
    return project


async def reset_analysis(session: SAAsyncSession) -> None:
    """Delete the demo project's seeded analysis rows so a subsequent seed refreshes the demo.

    The demo user, org, project and its membership are left intact; only per-run analysis data
    (runs + everything scoped to them or to the project) is removed. Safe when nothing is seeded yet.

    Uses a plain SQLAlchemy ``AsyncSession`` because the bulk ``delete()`` statements are issued via
    ``session.execute`` (the SQLModel session deprecates ``execute`` in favour of ``exec``, which only
    accepts selects).

    Args:
        session: Open plain SQLAlchemy async session.
    """
    project_id = _u("project", DEMO_ORG_SLUG, DEMO_PROJECT_SLUG)
    project = await _get(session, Project, project_id)
    if project is None:
        return

    run_ids = [_run_id(kind) for kind in _RUN_KINDS]
    dev_id = (await ensure_demo_user(session)).id

    # Assigned developers reference debt ids by discriminator column (no FK) → recompute + delete.
    code_run, kn_run = _run_id(JobType.CODE_DEBT_DETECTION), _run_id(JobType.KNOWLEDGE_DEBT_DETECTION)
    code_debt_ids = [_u("code_debt", code_run, fp, t) for fp, t, *_ in _CODE_DEBTS]
    kn_debt_ids = [_u("knowledge_debt", kn_run, fp, r) for fp, r, *_ in _KNOWLEDGE_DEBTS]
    if code_debt_ids:
        await session.execute(delete(AssignedDeveloper).where(col(AssignedDeveloper.debt_id).in_(code_debt_ids)))
    if kn_debt_ids:
        await session.execute(delete(AssignedDeveloper).where(col(AssignedDeveloper.debt_id).in_(kn_debt_ids)))

    # Learning plan + steps + resources (project-scoped).
    plan_id = _u("learning_plan", project_id, dev_id, "checkout")
    await session.execute(delete(LearningStep).where(col(LearningStep.plan_id) == plan_id))
    await session.execute(delete(LearningPlan).where(col(LearningPlan.project_id) == project_id))
    await session.execute(delete(LearningResource).where(col(LearningResource.project_id) == project_id))

    # Quiz session (project-scoped).
    await session.execute(delete(QuizSession).where(col(QuizSession.project_id) == project_id))

    # Run-scoped rows.
    await session.execute(delete(RepoFile).where(col(RepoFile.run_id).in_(run_ids)))
    await session.execute(delete(FileKc).where(col(FileKc.run_id).in_(run_ids)))
    await session.execute(delete(Dependency).where(col(Dependency.run_id).in_(run_ids)))
    await session.execute(delete(FeatureFile).where(col(FeatureFile.run_id).in_(run_ids)))
    await session.execute(delete(Feature).where(col(Feature.run_id).in_(run_ids)))
    await session.execute(delete(CodeDebt).where(col(CodeDebt.run_id).in_(run_ids)))
    await session.execute(delete(KnowledgeDebt).where(col(KnowledgeDebt.run_id).in_(run_ids)))

    # Project-scoped aggregates.
    await session.execute(delete(DebtTrendPoint).where(col(DebtTrendPoint.project_id) == project_id))
    await session.execute(delete(TechStack).where(col(TechStack.owner) == DEMO_REPO_OWNER))

    # The runs themselves last.
    await session.execute(delete(AnalysisRun).where(col(AnalysisRun.id).in_(run_ids)))
    await session.commit()


async def main(do_reset: bool) -> None:
    """Run the seeder (optionally resetting analysis rows first).

    Args:
        do_reset: When ``True``, delete the demo org's seeded analysis rows before re-seeding.
    """
    if do_reset:
        async with app_db.sa_async_session_maker() as sa_session:
            await reset_analysis(sa_session)
    async with app_db.async_session_maker() as session:
        await seed(session)
    suffix = " (reset)" if do_reset else ""
    print(f"seeded demo workspace: org={DEMO_ORG_SLUG!r} project={DEMO_PROJECT_SLUG!r}{suffix}")


def _parse_args() -> argparse.Namespace:
    """Parse the CLI arguments (positional ``reset`` subcommand)."""
    parser = argparse.ArgumentParser(description="Seed the guest-demo workspace (idempotent).")
    parser.add_argument(
        "command",
        nargs="?",
        default="seed",
        choices=["seed", "reset"],
        help="'seed' (default) or 'reset' (delete seeded analysis rows, then re-seed).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(do_reset=args.command == "reset"))
