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
import hashlib
import posixpath
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlmodel import col, select
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
    QuizAnswer,
    QuizResult,
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
DEMO_PROJECT_NAME = "EC ストア"
DEMO_REPO_OWNER = "devdebtops"
DEMO_REPO_NAME = "sample-shop"
DEMO_REPO_FULL_NAME = "devdebtops/sample-shop"
DEMO_DEFAULT_BRANCH = "main"

# Extra metadata-only projects so the sidebar has several to group into sections / star
# (issue 069 demo; the sections/stars themselves are client-side — frontend project-sections store).
# These carry no analysis rows; they exist to populate the project switcher.
_EXTRA_PROJECTS: list[tuple[str, str]] = [
    ("billing-service", "請求サービス"),
    ("inventory-api", "在庫API"),
    ("marketing-site", "マーケLP"),
    ("internal-tools", "社内ツール"),
    ("mobile-app", "モバイルアプリ"),
]

# The "現在" snapshot all latest-run screens read. A fixed commit so re-runs reuse the same runs.
_HEAD_COMMIT = "0691a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9"

# One analysis run per kind that the read endpoints look up as the "latest COMPLETED run".
_RUN_KINDS = (
    JobType.CODE_DEBT_DETECTION,
    JobType.KC_ANALYSIS,
    JobType.KNOWLEDGE_DEBT_DETECTION,
    JobType.FEATURE_CLUSTERING,
)

# Sample repository files (path → (language, loc, kc, code_debt_score)). KC は Overview 散布図の
# 横軸 / Galaxy file universe を、code_debt_score は縦軸（静的品質）を駆動する。両軸とも [0.1,0.9]
# に広く散らし、4 象限すべてに点が乗るよう調整（上端=低負債=クリーンへの偏りを解消）。各ファイルは
# _ensure_code_debts で 1 件の CodeDebt を持つため、散布図の縦位置は code_debt_score を直接反映する。
_CORE_FILES: list[tuple[str, str, int, float, float]] = [
    # checkout（決済・カート）— ホットスポット機能
    ("src/checkout/payment.py", "Python", 412, 0.18, 0.86),  # 最危険: 低 KC × 高コード負債
    ("src/checkout/cart.py", "Python", 233, 0.34, 0.60),
    ("src/checkout/order.py", "Python", 201, 0.45, 0.40),
    ("src/checkout/coupon.py", "Python", 96, 0.66, 0.30),
    ("src/ui/checkout-form.svelte", "Svelte", 98, 0.81, 0.14),  # 理想: 高 KC × クリーン
    # auth（認証）
    ("src/auth/session.py", "Python", 188, 0.27, 0.50),  # 知識ホットスポット
    ("src/auth/oauth.py", "Python", 145, 0.62, 0.34),
    ("src/auth/password.py", "Python", 88, 0.49, 0.56),
    ("src/auth/jwt.py", "Python", 76, 0.71, 0.20),
    ("src/ui/login.svelte", "Svelte", 120, 0.58, 0.12),
    # catalog（商品カタログ）
    ("src/catalog/search.ts", "TypeScript", 320, 0.21, 0.74),  # 危険: 低 KC × 高負債
    ("src/catalog/product.ts", "TypeScript", 176, 0.74, 0.26),  # 理解済み・クリーン
    ("src/catalog/category.ts", "TypeScript", 110, 0.63, 0.54),  # 要リファクタ: 高 KC × 高負債
    ("src/ui/product-card.svelte", "Svelte", 84, 0.78, 0.10),
    ("src/lib/db.py", "Python", 64, 0.55, 0.22),
    # inventory（在庫）
    ("src/inventory/stock.py", "Python", 167, 0.31, 0.66),
    ("src/inventory/warehouse.py", "Python", 142, 0.40, 0.38),
    ("src/inventory/reservation.py", "Python", 119, 0.24, 0.44),
    # user（ユーザー）
    ("src/user/profile.py", "Python", 134, 0.69, 0.46),
    ("src/user/address.py", "Python", 92, 0.57, 0.28),
    ("src/ui/profile-page.svelte", "Svelte", 110, 0.80, 0.18),
    # shipping（配送）
    ("src/shipping/shipping.py", "Python", 158, 0.37, 0.58),
    ("src/shipping/tracking.ts", "TypeScript", 124, 0.52, 0.70),  # 要リファクタ
    ("src/shipping/carrier.py", "Python", 101, 0.46, 0.42),
    # notifications（通知）
    ("src/notifications/email.py", "Python", 113, 0.61, 0.32),
    ("src/notifications/push.ts", "TypeScript", 97, 0.44, 0.62),
    ("src/notifications/templates.py", "Python", 78, 0.72, 0.36),
]

# Feature clusters (key, name, description, [member file paths]).
_CORE_FEATURES: list[tuple[str, str, str, list[str]]] = [
    (
        "checkout",
        "決済・カート",
        "カート操作から決済確定までの中核フロー。最も理解負債が集中するホットスポット。",
        [
            "src/checkout/payment.py",
            "src/checkout/cart.py",
            "src/checkout/order.py",
            "src/checkout/coupon.py",
            "src/ui/checkout-form.svelte",
        ],
    ),
    (
        "auth",
        "認証",
        "ログイン・セッション・OAuth・トークン発行。セッション管理に理解の空白が残る。",
        [
            "src/auth/session.py",
            "src/auth/oauth.py",
            "src/auth/password.py",
            "src/auth/jwt.py",
            "src/ui/login.svelte",
        ],
    ),
    (
        "catalog",
        "商品カタログ",
        "商品検索・一覧・カテゴリ。検索ロジックにコード負債が溜まっている。",
        [
            "src/catalog/search.ts",
            "src/catalog/product.ts",
            "src/catalog/category.ts",
            "src/ui/product-card.svelte",
            "src/lib/db.py",
        ],
    ),
    (
        "inventory",
        "在庫",
        "在庫・倉庫・引当。決済と密結合で、引当ロジックの理解が薄い。",
        ["src/inventory/stock.py", "src/inventory/warehouse.py", "src/inventory/reservation.py"],
    ),
    (
        "user",
        "ユーザー",
        "プロフィール・住所管理。認証と連携する。",
        ["src/user/profile.py", "src/user/address.py", "src/ui/profile-page.svelte"],
    ),
    (
        "shipping",
        "配送",
        "配送・追跡・キャリア連携。決済完了後のフロー。",
        ["src/shipping/shipping.py", "src/shipping/tracking.ts", "src/shipping/carrier.py"],
    ),
    (
        "notifications",
        "通知",
        "メール・プッシュ通知とテンプレート。各機能から呼ばれる横断機能。",
        ["src/notifications/email.py", "src/notifications/push.ts", "src/notifications/templates.py"],
    ),
]

# Intra-repo import edges (wormholes) for the galaxy. Mix of intra-feature (L2 のファイルグラフ) と
# 機能をまたぐ依存（L1 の機能間エッジになる）を持たせて、グラフらしい接続にする。
_CORE_DEPENDENCIES: list[tuple[str, str]] = [
    # checkout 内部
    ("src/checkout/payment.py", "src/checkout/cart.py"),
    ("src/checkout/cart.py", "src/checkout/order.py"),
    ("src/checkout/payment.py", "src/checkout/coupon.py"),
    ("src/checkout/order.py", "src/checkout/payment.py"),
    ("src/ui/checkout-form.svelte", "src/checkout/cart.py"),
    # auth 内部
    ("src/ui/login.svelte", "src/auth/session.py"),
    ("src/auth/oauth.py", "src/auth/session.py"),
    ("src/auth/session.py", "src/auth/jwt.py"),
    ("src/auth/password.py", "src/auth/session.py"),
    # catalog 内部
    ("src/catalog/search.ts", "src/catalog/product.ts"),
    ("src/catalog/product.ts", "src/catalog/category.ts"),
    ("src/catalog/search.ts", "src/lib/db.py"),
    ("src/ui/product-card.svelte", "src/catalog/product.ts"),
    # inventory 内部
    ("src/inventory/reservation.py", "src/inventory/stock.py"),
    ("src/inventory/warehouse.py", "src/inventory/stock.py"),
    # user 内部
    ("src/user/profile.py", "src/user/address.py"),
    ("src/ui/profile-page.svelte", "src/user/profile.py"),
    # shipping 内部
    ("src/shipping/shipping.py", "src/shipping/carrier.py"),
    ("src/shipping/tracking.ts", "src/shipping/shipping.py"),
    # notifications 内部
    ("src/notifications/email.py", "src/notifications/templates.py"),
    ("src/notifications/push.ts", "src/notifications/templates.py"),
    # 機能をまたぐ依存（L1 の機能間エッジ）
    ("src/checkout/payment.py", "src/auth/session.py"),
    ("src/checkout/payment.py", "src/inventory/reservation.py"),
    ("src/checkout/cart.py", "src/inventory/stock.py"),
    ("src/checkout/cart.py", "src/catalog/product.ts"),
    ("src/checkout/order.py", "src/shipping/shipping.py"),
    ("src/checkout/order.py", "src/notifications/email.py"),
    ("src/catalog/product.ts", "src/inventory/stock.py"),
    ("src/user/profile.py", "src/auth/session.py"),
    ("src/shipping/shipping.py", "src/user/address.py"),
    ("src/notifications/email.py", "src/user/profile.py"),
]

# --- デモ拡張（issue: 理解度マップが薄い）------------------------------------------------------------
# 実リポジトリらしい規模感（〜200 ノード）にするため、キュレーション済みのコア機能に加えて EC ストアの
# 追加ドメインを生成する。件数・KC・依存はすべて**決定的**（パス由来のハッシュ）に導出し、再シードしても
# 同じデータ（＝uuid5 の id 安定）になるようにする。KC は理解済み/部分/未理解/未着手が混ざる分布にして、
# 理解度マップの色が偏らず「見栄え」するようにする。
#
# (feature key, 表示名, 説明, ディレクトリ, [basename.ext, ...])
_EXTRA_FEATURES: list[tuple[str, str, str, str, list[str]]] = [
    (
        "payments",
        "決済ゲートウェイ",
        "外部決済(Stripe/PayPal)連携・返金・Webhook・照合。決済の中核と密結合。",
        "src/payments",
        [
            "gateway.py",
            "stripe.py",
            "paypal.py",
            "refund.py",
            "webhook.py",
            "capture.py",
            "currency.py",
            "receipt.py",
            "fraud_check.py",
            "retry_policy.py",
            "ledger.py",
            "reconcile.py",
            "settlement.py",
        ],
    ),
    (
        "orders",
        "注文管理",
        "注文の作成・状態遷移・返品/キャンセル・履歴。決済/配送/在庫をつなぐハブ。",
        "src/orders",
        [
            "order_service.py",
            "order_repository.py",
            "order_state.py",
            "invoice.py",
            "returns.py",
            "cancellation.py",
            "fulfillment.py",
            "order_events.py",
            "order_api.ts",
            "order_history.py",
            "order_search.ts",
            "order_export.py",
        ],
    ),
    (
        "reviews",
        "レビュー・評価",
        "商品レビュー・評価・モデレーション・スパム判定。",
        "src/reviews",
        [
            "review.py",
            "rating.py",
            "moderation.py",
            "review_api.ts",
            "review-list.svelte",
            "helpfulness.py",
            "spam_filter.py",
            "review_repository.py",
            "review-form.svelte",
        ],
    ),
    (
        "recommendations",
        "レコメンド",
        "協調フィルタ/コンテンツベースの推薦・ランキング・類似度。",
        "src/reco",
        [
            "engine.py",
            "collaborative.py",
            "content_based.py",
            "ranking.py",
            "feature_store.py",
            "popular.py",
            "reco_api.ts",
            "embeddings.py",
            "similarity.py",
            "reco-widget.svelte",
        ],
    ),
    (
        "promotions",
        "プロモーション",
        "キャンペーン・割引・クーポン・ロイヤリティ・A/B テスト。",
        "src/promotions",
        [
            "campaign.py",
            "discount.py",
            "coupon_engine.py",
            "banner.ts",
            "promo-banner.svelte",
            "ab_test.py",
            "loyalty.py",
            "points.py",
            "gift_card.py",
        ],
    ),
    (
        "admin",
        "管理画面",
        "管理ダッシュボード・ユーザー/注文/カタログ管理・監査ログ・権限。",
        "src/admin",
        [
            "dashboard.svelte",
            "admin_api.ts",
            "users_admin.py",
            "orders_admin.py",
            "catalog_admin.py",
            "audit_log.py",
            "roles.py",
            "admin-table.svelte",
            "settings-page.svelte",
            "permissions_admin.py",
            "reports_admin.py",
        ],
    ),
    (
        "analytics",
        "分析・計測",
        "イベント計測・集計パイプライン・レポート・ファネル/コホート。",
        "src/analytics",
        [
            "tracker.ts",
            "events.py",
            "pipeline.py",
            "report.py",
            "funnel.py",
            "cohort.py",
            "dashboard_api.ts",
            "aggregate.py",
            "export_csv.py",
            "realtime.ts",
        ],
    ),
    (
        "search",
        "検索・インデックス",
        "検索インデックス・クエリ解析・ランキング・サジェスト・ファセット。",
        "src/search",
        [
            "indexer.py",
            "query_parser.py",
            "ranker.py",
            "synonyms.py",
            "facets.py",
            "suggest.ts",
            "elastic_client.py",
            "tokenizer.py",
            "highlight.py",
        ],
    ),
    (
        "cms",
        "コンテンツ管理",
        "CMS ページ/ブロック・メディア・SEO・サイトマップ。",
        "src/cms",
        [
            "page.py",
            "block.py",
            "editor.svelte",
            "media.py",
            "seo.py",
            "sitemap.py",
            "render.ts",
            "cms_api.ts",
            "navigation.py",
        ],
    ),
    (
        "platform",
        "共通基盤",
        "設定・ロギング・キャッシュ・HTTP・イベントバス・API ルーティング等の横断基盤。",
        "src/core",
        [
            "config.py",
            "logger.py",
            "cache.py",
            "http_client.py",
            "errors.py",
            "validators.py",
            "pagination.py",
            "event_bus.py",
            "feature_flags.py",
            "metrics.py",
            "serializers.py",
            "middleware.py",
            "db_session.py",
            "routes.py",
            "deps.py",
            "health.py",
        ],
    ),
    (
        "models",
        "データモデル",
        "ORM モデル・スキーマ・共通 Mixin。各ドメインから参照される。",
        "src/models",
        [
            "user.py",
            "order.py",
            "product.py",
            "cart.py",
            "payment.py",
            "review.py",
            "base.py",
            "mixins.py",
            "inventory.py",
            "shipment.py",
        ],
    ),
    (
        "ui-kit",
        "UI 部品",
        "共通 UI コンポーネント（ボタン/モーダル/テーブル等）と多言語。",
        "src/ui/components",
        [
            "button.svelte",
            "modal.svelte",
            "data-table.svelte",
            "form-field.svelte",
            "toast.svelte",
            "nav-bar.svelte",
            "pagination.svelte",
            "card.svelte",
            "badge.svelte",
            "spinner.svelte",
            "tabs.svelte",
            "tooltip.svelte",
            "dropdown.svelte",
        ],
    ),
    (
        "ops",
        "運用・外部連携・セキュリティ",
        "ジョブ/キュー・ERP/CRM 連携・ストレージ・CSRF/暗号化など運用面。",
        "src/ops",
        [
            "worker.py",
            "queue.py",
            "scheduler.py",
            "email_job.py",
            "reindex_job.py",
            "cleanup_job.py",
            "dead_letter.py",
            "erp_sync.py",
            "crm_sync.py",
            "webhook_dispatcher.py",
            "s3_storage.py",
            "sendgrid.ts",
            "twilio.py",
            "csrf.py",
            "rate_limiter.py",
            "encryption.py",
        ],
    ),
    (
        "pricing",
        "価格計算",
        "価格・税・為替・端数処理・バンドル・マージン。",
        "src/pricing",
        ["pricing.py", "tax.py", "currency_rates.py", "rounding.py", "price_rules.py", "bundle.py", "margin.py"],
    ),
    (
        "wishlist",
        "お気に入り",
        "ウィッシュリスト・共有・再入荷通知。",
        "src/wishlist",
        ["wishlist.py", "wishlist_api.ts", "wishlist-page.svelte", "share.py", "notify_back_in_stock.py"],
    ),
    (
        "support",
        "サポート",
        "問い合わせチケット・チャット・FAQ・エスカレーション。",
        "src/support",
        ["ticket.py", "chat.ts", "faq.py", "support-widget.svelte", "escalation.py", "knowledge_base.py"],
    ),
]

# 追加機能のハブを、意味的に近いコア/追加ファイルへつなぐ機能間エッジ（グラフを 1 つに連結し密度を上げる）。
_EXTRA_CROSS: list[tuple[str, str]] = [
    ("payments", "src/checkout/payment.py"),
    ("orders", "src/checkout/order.py"),
    ("reviews", "src/catalog/product.ts"),
    ("recommendations", "src/catalog/search.ts"),
    ("promotions", "src/checkout/coupon.py"),
    ("admin", "src/auth/session.py"),
    ("analytics", "src/orders/order_events.py"),
    ("search", "src/catalog/search.ts"),
    ("cms", "src/catalog/category.ts"),
    ("models", "src/lib/db.py"),
    ("ui-kit", "src/ui/product-card.svelte"),
    ("ops", "src/notifications/email.py"),
    ("pricing", "src/checkout/order.py"),
    ("wishlist", "src/user/profile.py"),
    ("support", "src/user/profile.py"),
    # 多くのドメインが共通基盤(platform)に依存 → 中心ハブとして連結性を高める。
    ("payments", "src/core/config.py"),
    ("orders", "src/core/db_session.py"),
    ("search", "src/core/cache.py"),
    ("analytics", "src/core/event_bus.py"),
    ("reviews", "src/models/review.py"),
    ("orders", "src/models/order.py"),
    ("payments", "src/models/payment.py"),
]

_EXT_LANG = {"py": "Python", "ts": "TypeScript", "tsx": "TSX", "svelte": "Svelte", "js": "JavaScript"}


def _lang_of(basename: str) -> str:
    return _EXT_LANG.get(basename.rsplit(".", 1)[-1], "Python")


def _det01(salt: str, path: str) -> float:
    """Deterministic float in [0,1) from (salt, path) — stable across re-seeds (no RNG)."""
    return (int(hashlib.md5(f"{salt}:{path}".encode()).hexdigest()[:8], 16) % 1000) / 1000


def _kc_of(path: str) -> float:
    """Varied but deterministic KC so map colors are a mix (理解済み/部分/未理解/未着手)."""
    if _det01("kc", path) < 0.10:
        return 0.0  # ~10% は未着手（unexplored / グレー）
    return round(0.12 + _det01("kcv", path) * 0.83, 2)  # 0.12〜0.95 に分布


def _build_extra() -> tuple[list, list, list]:
    files: list[tuple[str, str, int, float, float]] = []
    features: list[tuple[str, str, str, list[str]]] = []
    deps: list[tuple[str, str]] = []
    hub: dict[str, str] = {}
    for key, name, desc, directory, basenames in _EXTRA_FEATURES:
        paths = [f"{directory}/{bn}" for bn in basenames]
        for p in paths:
            files.append(
                (
                    p,
                    _lang_of(p.rsplit("/", 1)[-1]),
                    40 + int(_det01("loc", p) * 360),
                    _kc_of(p),
                    round(_det01("score", p) * 0.9, 2),
                )
            )
        features.append((key, name, desc, paths))
        hub[key] = paths[0]
        for i in range(1, len(paths)):
            deps.append((paths[i], paths[i - 1]))  # 機能内チェーン
            if i >= 2:
                deps.append((paths[i], paths[0]))  # ハブへも張って密度を上げる
    for key, target in _EXTRA_CROSS:
        if key in hub:
            deps.append((hub[key], target))
    return files, features, deps


_extra_files, _extra_features, _extra_deps = _build_extra()

# 最終データ = キュレーション済みコア + 生成した追加ドメイン（合計 〜200 ファイル）。
_FILES: list[tuple[str, str, int, float, float]] = _CORE_FILES + _extra_files
_FEATURES: list[tuple[str, str, str, list[str]]] = _CORE_FEATURES + _extra_features
_DEPENDENCIES: list[tuple[str, str]] = _CORE_DEPENDENCIES + _extra_deps

# Code-debt findings (file_path, type, severity, score, ai_prob, repay_hours, notes).
_CODE_DEBTS: list[tuple[str, str, str, float, float, float, str]] = [
    (
        "src/checkout/payment.py",
        "complexity",
        "critical",
        0.86,
        0.71,
        6.0,
        "条件分岐が深く入れ子になっていて、処理の流れを追うのが難しい状態です。",
    ),
    (
        "src/catalog/search.ts",
        "duplicate",
        "high",
        0.74,
        0.44,
        3.5,
        "検索フィルタを組み立てるほぼ同じ処理が複数箇所に重複しています。",
    ),
    (
        "src/checkout/cart.py",
        "complexity",
        "medium",
        0.60,
        0.33,
        2.0,
        "在庫引当の条件分岐が多く、どの場合にどう動くのか把握しづらくなっています。",
    ),
    (
        "src/auth/session.py",
        "dead",
        "medium",
        0.50,
        0.12,
        1.5,
        "どこからも呼ばれていない古いセッション検証のコードが残ったままになっています。",
    ),
    (
        "src/lib/db.py",
        "other",
        "low",
        0.22,
        0.05,
        0.5,
        "型の情報が不足し、例外も握り潰されているため不具合に気づきにくい状態です。",
    ),
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
    "src/inventory/stock.py": (
        "def reserve(sku, qty):\n"
        "    level = STOCK.get(sku, 0)\n"
        "    if level < qty:\n"
        "        raise OutOfStock(sku)  # 在庫チェックと引当が非アトミック（競合の余地）\n"
        "    STOCK[sku] = level - qty\n"
        "    return Reservation(sku, qty)\n"
    ),
    "src/user/profile.py": (
        "def update_profile(user_id, patch):\n"
        "    user = load(user_id)\n"
        "    for k, v in patch.items():\n"
        "        setattr(user, k, v)  # 入力検証なしで全フィールドを上書き（mass assignment）\n"
        "    save(user)\n"
    ),
    "src/shipping/shipping.py": (
        "def create_shipment(order):\n"
        "    carrier = pick_carrier(order.region)\n"
        "    label = carrier.create_label(order)  # 失敗時のリトライ/補償が未実装\n"
        "    order.tracking = label.tracking_no\n"
        "    return label\n"
    ),
    "src/notifications/email.py": (
        "def send_order_email(order):\n"
        "    tpl = TEMPLATES['order_confirm']\n"
        "    body = tpl.format(**order.__dict__)  # テンプレ変数の欠落で KeyError の恐れ\n"
        "    smtp.send(order.email, body)\n"
    ),
    # --- 各機能のクイズが参照する追加ソース（機能ごとに実在ファイルの断片を見せる）--------------------
    "src/checkout/order.py": (
        "def place_order(cart, user):\n"
        "    order = Order(user_id=user.id, items=cart.items)\n"
        "    order.total = sum(i.price * i.qty for i in cart.items)  # クーポン/税/送料を未加味\n"
        "    db.add(order)\n"
        "    db.commit()  # 決済確定前にコミット → 失敗すると未払い注文が残る\n"
        "    return order\n"
    ),
    "src/checkout/coupon.py": (
        "def apply_coupon(order, code):\n"
        "    coupon = COUPONS.get(code)\n"
        "    if coupon and coupon.active:\n"
        "        order.total -= coupon.amount  # 下限チェックなし → 合計が負になり得る\n"
        "    return order.total\n"
    ),
    "src/auth/oauth.py": (
        "def handle_callback(request):\n"
        "    code = request.args['code']\n"
        "    token = exchange_code(code)  # state を検証しておらず CSRF の余地\n"
        "    profile = fetch_profile(token)\n"
        "    return login_or_create(profile.email)  # メール検証前にアカウント連携\n"
    ),
    "src/auth/password.py": (
        "import hashlib\n"
        "\n"
        "def hash_password(raw):\n"
        "    return hashlib.md5(raw.encode()).hexdigest()  # ソルトなし・高速ハッシュで総当たりに弱い\n"
        "\n"
        "def verify_password(raw, stored):\n"
        "    return hash_password(raw) == stored\n"
    ),
    "src/auth/jwt.py": (
        "def decode_token(token):\n"
        "    header, payload, sig = token.split('.')\n"
        "    claims = json.loads(b64decode(payload))\n"
        "    return claims  # 署名(sig) も exp も検証せず → 改ざん・期限切れを見逃す\n"
    ),
    "src/catalog/product.ts": (
        "export async function getProduct(id: string): Promise<Product> {\n"
        "  const p = await db.query(`SELECT * FROM products WHERE id = ${id}`); // 文字列連結で SQL インジェクション\n"
        "  p.reviews = await db.query(`SELECT * FROM reviews WHERE product_id = ${id}`); // 商品ごとに追加クエリ(N+1)\n"
        "  return p;\n"
        "}\n"
    ),
    "src/catalog/category.ts": (
        "export function buildTree(cats: Category[]): Node[] {\n"
        "  return cats.map((c) => ({\n"
        "    ...c,\n"
        "    children: cats.filter((x) => x.parentId === c.id).map(toNode), // O(n^2)・孫階層が欠落\n"
        "  }));\n"
        "}\n"
    ),
    "src/inventory/warehouse.py": (
        "def pick_warehouse(order):\n"
        "    for wh in WAREHOUSES:\n"
        "        if wh.region == order.region:\n"
        "            return wh  # 在庫の有無を見ず地域一致だけで選定（欠品倉庫を返し得る）\n"
        "    return WAREHOUSES[0]  # 暗黙のフォールバックで遠隔倉庫に割り当たる\n"
    ),
    "src/inventory/reservation.py": (
        "def reserve_for_order(order):\n"
        "    holds = []\n"
        "    for item in order.items:\n"
        "        holds.append(reserve(item.sku, item.qty))  # 途中失敗で確保済みが解放されない（部分確保のリーク）\n"
        "    return holds\n"
    ),
    "src/user/address.py": (
        "def save_address(user_id, data):\n"
        "    addr = Address(**data)  # 郵便番号・国コードの検証なしで保存\n"
        "    addr.user_id = user_id\n"
        "    db.add(addr)\n"
        "    db.commit()\n"
        "    return addr\n"
    ),
    "src/shipping/tracking.ts": (
        "export async function poll(trackingNo: string) {\n"
        "  while (true) {                       // 終了条件なしの無限ポーリング（配達済みでも止まらない）\n"
        "    const s = await carrier.status(trackingNo);\n"
        "    await sleep(1000);                 // バックオフなしで毎秒外部 API を叩く\n"
        "    update(trackingNo, s);\n"
        "  }\n"
        "}\n"
    ),
    "src/shipping/carrier.py": (
        "def create_label(order):\n"
        "    resp = requests.post(CARRIER_URL, json=order.to_dict())  # タイムアウト未設定でハングし得る\n"
        "    return resp.json()['tracking_no']  # 失敗レスポンス(4xx/5xx)を確認せず KeyError の恐れ\n"
    ),
    "src/notifications/push.ts": (
        "export async function pushAll(userIds: string[], msg: Message) {\n"
        "  for (const id of userIds) {\n"
        "    await device.send(id, msg);  // 直列送信で件数に比例して遅延、失敗時のリトライもなし\n"
        "  }\n"
        "}\n"
    ),
    "src/notifications/templates.py": (
        "def render(name, ctx):\n"
        "    tpl = TEMPLATES[name]           # 未知のテンプレ名で KeyError\n"
        "    return tpl % ctx                # % 書式は欠損キー・型不一致に弱い\n"
    ),
}


def _snippet_for(file_path: str, dtype: str) -> str:
    """Return a realistic-looking source snippet for a demo file.

    Curated files use ``_DEMO_SNIPPETS``; everything else gets a plausible snippet generated from the
    file extension (.py / .ts / .svelte) and debt ``type`` (dead / duplicate / complexity / other), so the
    detail page never shows a "デモ用ダミー" placeholder.
    """
    stem = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    ext = file_path.rsplit(".", 1)[-1]
    snake = stem.replace("-", "_")
    pascal = "".join(p.capitalize() for p in snake.split("_"))

    if ext == "py":
        if dtype == "complexity":
            return (
                f"def {snake}(ctx, *, retries=3):\n"
                "    if ctx.enabled:\n"
                "        for item in ctx.items:\n"
                "            if item.valid and not item.skip:\n"
                "                if item.weight > threshold(ctx):\n"
                "                    apply(item)  # 深いネスト / 循環的複雑度が高い\n"
                "    return ctx.result\n"
            )
        if dtype == "duplicate":
            return (
                f"def {snake}_a(x):\n"
                "    return normalize(x.field) if x.field else default()  # 重複ブロック (1/3)\n\n"
                f"def {snake}_b(x):\n"
                "    return normalize(x.field) if x.field else default()  # 重複ブロック (2/3)\n\n"
                f"def {snake}_c(x):\n"
                "    return normalize(x.field) if x.field else default()  # 重複ブロック (3/3)\n"
            )
        if dtype == "dead":
            return (
                f"def {snake}(req):\n"
                "    return handle(req)\n\n"
                f"def _legacy_{snake}(req):  # どこからも呼ばれない未到達パス（dead）\n"
                "    return req.get('legacy')\n"
            )
        return (
            f"def {snake}(query, params):\n"
            "    try:\n"
            "        return run(query, params)\n"
            "    except Exception:\n"
            "        pass  # 例外の握り潰し / 戻り値の型ヒント欠落\n"
        )

    if ext in ("ts", "tsx", "js"):
        if dtype == "complexity":
            return (
                f"export function {snake}(input: Input): Result {{\n"
                "  if (input.enabled) {\n"
                "    for (const it of input.items) {\n"
                "      if (it.valid && !it.skip) {\n"
                "        if (it.weight > threshold(input)) apply(it); // 深いネスト / 複雑度が高い\n"
                "      }\n"
                "    }\n"
                "  }\n"
                "  return input.result;\n"
                "}\n"
            )
        if dtype == "duplicate":
            return (
                "function mapA(q: Query) { return q.field ? norm(q.field) : def(); } // 重複 (1/3)\n"
                "function mapB(q: Query) { return q.field ? norm(q.field) : def(); } // 重複 (2/3)\n"
                "function mapC(q: Query) { return q.field ? norm(q.field) : def(); } // 重複 (3/3)\n"
            )
        if dtype == "dead":
            return (
                f"export function {snake}(req: Req) {{\n  return handle(req);\n}}\n\n"
                f"function legacy{pascal}(req: Req) {{ // 未使用・未到達（dead）\n  return req.legacy;\n}}\n"
            )
        return (
            f"export function {snake}(data: any) {{ // any 型 / エラー握り潰し\n"
            "  try {\n"
            "    return parse(data);\n"
            "  } catch {\n"
            "    return null;\n"
            "  }\n"
            "}\n"
        )

    # .svelte（種別に応じたにおいのコメントを添える）
    smell = {
        "complexity": "テンプレートとロジックが密結合で分岐が多い",
        "duplicate": "近接コンポーネントとマークアップが重複",
        "dead": "参照されない props / 到達しないブロックあり",
        "other": "型注釈が緩く副作用が見通しにくい",
    }.get(dtype, "軽微な品質の問題あり")
    return (
        '<script lang="ts">\n'
        f"  // {stem}.svelte — {smell}\n"
        "  export let data;\n"
        "  function handle() {\n"
        "    /* ... */\n"
        "  }\n"
        "</script>\n\n"
        "<div on:click={handle}>{data?.label}</div>\n"
    )


_LANG_BY_EXT = {"py": "python", "ts": "typescript", "tsx": "tsx", "svelte": "svelte", "js": "javascript"}


def _code_snippet(path: str) -> dict:
    """Build a quiz ``code_snippet`` dict from a seeded demo file (reuses its realistic source)."""
    ext = path.rsplit(".", 1)[-1]
    return {
        "language": _LANG_BY_EXT.get(ext, "text"),
        "path": path,
        "content": _DEMO_SNIPPETS.get(path) or _snippet_for(path, "other"),
    }


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
        "prompt": "payment.py の confirm_payment で mark_paid（確定）が失敗したとき、正しい後始末はどれ？",
        "code_snippet": _code_snippet("src/checkout/payment.py"),
        "choices": [
            {"id": "a", "label": "課金をロールバックしてから失敗を返す"},
            {"id": "b", "label": "そのまま True を返して成功扱いにする"},
            {"id": "c", "label": "在庫だけ解放して課金は放置する"},
            {"id": "d", "label": "mark_paid を無限にリトライする"},
        ],
        "difficulty": "L3",
    },
    {
        "id": "q2",
        "kind": "multiple_choice",
        "prompt": "confirm_payment はガード条件で弾かれた場合も末尾で True を返す。この設計の問題はどれ？",
        "code_snippet": _code_snippet("src/checkout/payment.py"),
        "choices": [
            {"id": "a", "label": "何も課金していないのに呼び出し側が成功と誤認する"},
            {"id": "b", "label": "特に問題はない"},
            {"id": "c", "label": "処理が遅くなるだけ"},
            {"id": "d", "label": "ログが増えるだけ"},
        ],
        "difficulty": "L3",
    },
    {
        "id": "q3",
        "kind": "multiple_choice",
        "prompt": "coupon.py の apply_coupon に潜む不具合はどれ？",
        "code_snippet": _code_snippet("src/checkout/coupon.py"),
        "choices": [
            {"id": "a", "label": "下限チェックがなく、合計金額が負になり得る"},
            {"id": "b", "label": "クーポンを二重に適用している"},
            {"id": "c", "label": "有効期限を見ていない点だけが問題"},
            {"id": "d", "label": "問題はない"},
        ],
        "difficulty": "L2",
    },
    {
        "id": "q4",
        "kind": "multiple_choice",
        "prompt": "order.py の place_order で、決済確定前に db.commit している点の問題はどれ？",
        "code_snippet": _code_snippet("src/checkout/order.py"),
        "choices": [
            {"id": "a", "label": "決済に失敗すると未払いの注文が DB に残る"},
            {"id": "b", "label": "コミットが遅くなるだけ"},
            {"id": "c", "label": "在庫が二重に減る"},
            {"id": "d", "label": "問題はない"},
        ],
        "difficulty": "L3",
    },
    {
        "id": "q5",
        "kind": "multiple_select",
        "prompt": "この決済フローで冪等性を担保するために必要な要素をすべて選べ。",
        "code_snippet": _code_snippet("src/checkout/payment.py"),
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
    "q1": {"answer": "a", "rubric": "確定失敗時は課金を巻き戻して不整合を防ぐ。"},
    "q2": {"answer": "a", "rubric": "何も処理していない経路で成功を返すのは誤り。状態ごとに明示的な戻り値を返す。"},
    "q3": {"answer": "a", "rubric": "割引後の下限（0 以上）を保証しないと合計が負になる。"},
    "q4": {"answer": "a", "rubric": "決済確定までコミットを遅延し、失敗時はロールバックする。"},
    "q5": {"answer": ["a", "b", "d"], "rubric": "冪等キー・重複検出・状態永続化が必須。"},
}

# Learning plan (gap concepts + ordered steps → resources). Team assets先頭の閉ループを表現する。
_PLAN_GAP_CONCEPTS = ["決済の冪等性", "在庫引当のトランザクション境界", "セッション失効の設計"]
# Resource dict keys: key / origin / section / kind / title / summary / tech / url / minutes / priority /
# source_ref. section="code" + source_ref のリソースはクリックでコード理解ウォークスルーへ遷移する
# （デモはシード済みのソース＝origin_meta["demo_source"] をその場で表示し GitHub を読まない）。
_PLAN_RESOURCES: list[dict] = [
    {
        "key": "payment",
        "origin": "team",
        "section": "code",
        "kind": "code",
        "title": "決済確定フロー: payment.py を読む",
        "summary": "課金と在庫引当の順序・冪等性の要。失敗時にどう巻き戻すかを読み解く。",
        "tech": "",
        "url": None,
        "minutes": 15,
        "priority": "required",
        "source_ref": "src/checkout/payment.py",
    },
    {
        "key": "cart",
        "origin": "team",
        "section": "code",
        "kind": "code",
        "title": "在庫引当ロジック: cart.py を読む",
        "summary": "在庫引当の分岐とトランザクション境界。決済との密結合ポイントを把握する。",
        "tech": "",
        "url": None,
        "minutes": 10,
        "priority": "recommended",
        "source_ref": "src/checkout/cart.py",
    },
    {
        "key": "fastapi-deps",
        "origin": "external",
        "section": "stack",
        "kind": "docs",
        "title": "FastAPI 公式: Dependencies",
        "summary": "DI の依存解決順序を学び、セッション/認可の組み立てを理解する。",
        "tech": "FastAPI",
        "url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
        "minutes": 20,
        "priority": "supplementary",
        "source_ref": None,
    },
]


# Per-feature curated content (issue: enrich the demo so sample-shop looks like a real connected repo).
# Each core feature gets its own realistic quiz (with code snippets from its seeded files) and a learning
# plan (a code walkthrough of a representative file + tech-appropriate external docs). Checkout keeps its
# dedicated constants above; the long-tail _EXTRA_FEATURES fall back to the generic set below.
_FEATURE_CONTENT: dict[str, dict] = {
    "auth": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "session.py の validate_session で、期限切れのトークンはどう扱うべき？",
                "code_snippet": _code_snippet("src/auth/session.py"),
                "choices": [
                    {"id": "a", "label": "None を返し、呼び出し側で再認証させる"},
                    {"id": "b", "label": "期限を無視してそのまま通す"},
                    {"id": "c", "label": "例外を握り潰して真を返す"},
                    {"id": "d", "label": "クライアントの時刻を信用して延長する"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q2",
                "kind": "multiple_choice",
                "prompt": "password.py の hash_password に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/auth/password.py"),
                "choices": [
                    {"id": "a", "label": "ソルトなしの高速ハッシュ(MD5)で総当たり・レインボーテーブルに弱い"},
                    {"id": "b", "label": "ハッシュが遅すぎて実用にならない"},
                    {"id": "c", "label": "特に問題はない"},
                    {"id": "d", "label": "戻り値の型が誤っている"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "jwt.py の decode_token が見落としている検証はどれ？",
                "code_snippet": _code_snippet("src/auth/jwt.py"),
                "choices": [
                    {"id": "a", "label": "署名(sig)と有効期限(exp)の検証（改ざん・失効を見逃す）"},
                    {"id": "b", "label": "Base64 のデコード"},
                    {"id": "c", "label": "JSON のパース"},
                    {"id": "d", "label": "トークンの分割"},
                ],
                "difficulty": "L4",
            },
            {
                "id": "q4",
                "kind": "multiple_choice",
                "prompt": "oauth.py の handle_callback に潜むセキュリティ上の問題はどれ？",
                "code_snippet": _code_snippet("src/auth/oauth.py"),
                "choices": [
                    {"id": "a", "label": "state を検証しておらず CSRF、メール検証前に連携している"},
                    {"id": "b", "label": "認可コードを使っている点"},
                    {"id": "c", "label": "プロフィールを取得している点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L4",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "期限切れは無効化し再認証へ導くのが正解。"},
            "q2": {"answer": "a", "rubric": "ソルト付きの遅いハッシュ（bcrypt/argon2）が定石。MD5 は不可。"},
            "q3": {"answer": "a", "rubric": "署名と exp を検証しないと改ざん・期限切れトークンを受理してしまう。"},
            "q4": {"answer": "a", "rubric": "state 検証で CSRF を防ぎ、メール検証済みか確認してから連携する。"},
        },
        "gap_concepts": ["セッション失効の設計", "OAuth コールバックの検証", "JWT の署名と失効"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "セッション検証: session.py を読む",
                "summary": "トークンの検証・失効の扱いと、認可の組み立てを読み解く。",
                "tech": "",
                "url": None,
                "minutes": 12,
                "priority": "required",
                "source_ref": "src/auth/session.py",
            },
            {
                "key": "jwt",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "JWT 入門（jwt.io）",
                "summary": "署名・クレーム・失効の基礎を理解する。",
                "tech": "JWT",
                "url": "https://jwt.io/introduction",
                "minutes": 15,
                "priority": "recommended",
                "source_ref": None,
            },
            {
                "key": "oauth",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "OAuth 2.0 概要",
                "summary": "認可コードフローとコールバック検証の要点。",
                "tech": "OAuth",
                "url": "https://oauth.net/2/",
                "minutes": 20,
                "priority": "supplementary",
                "source_ref": None,
            },
        ],
    },
    "catalog": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "search.ts の buildFilters に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/catalog/search.ts"),
                "choices": [
                    {"id": "a", "label": "ほぼ同一のフィルタ組み立てが重複しており共通化すべき"},
                    {"id": "b", "label": "特に問題はない"},
                    {"id": "c", "label": "型が厳しすぎる"},
                    {"id": "d", "label": "分岐が少なすぎる"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q2",
                "kind": "multiple_select",
                "prompt": "product.ts の getProduct に潜む問題をすべて選べ。",
                "code_snippet": _code_snippet("src/catalog/product.ts"),
                "choices": [
                    {"id": "a", "label": "文字列連結のクエリで SQL インジェクションの恐れ"},
                    {"id": "b", "label": "商品ごとにレビューを追加取得しており N+1"},
                    {"id": "c", "label": "async/await を使っている点"},
                    {"id": "d", "label": "Promise を返している点"},
                ],
                "difficulty": "L4",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "db.py の fetch_one が不具合を見えにくくしている原因はどれ？",
                "code_snippet": _code_snippet("src/lib/db.py"),
                "choices": [
                    {"id": "a", "label": "例外を握り潰し、戻り値の型も不明で失敗に気づけない"},
                    {"id": "b", "label": "クエリを実行している点"},
                    {"id": "c", "label": "first() を呼んでいる点"},
                    {"id": "d", "label": "引数を 2 つ取る点"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q4",
                "kind": "multiple_choice",
                "prompt": "category.ts の buildTree の性能・正しさの問題はどれ？",
                "code_snippet": _code_snippet("src/catalog/category.ts"),
                "choices": [
                    {"id": "a", "label": "全件を毎回 filter する O(n^2) で、孫階層も欠落する"},
                    {"id": "b", "label": "map を使っている点"},
                    {"id": "c", "label": "スプレッド構文を使っている点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "重複したフィルタ生成は共通化して修正漏れを防ぐ。"},
            "q2": {"answer": ["a", "b"], "rubric": "パラメータ化クエリと結合/一括取得で SQLi と N+1 を解消する。"},
            "q3": {"answer": "a", "rubric": "例外の握り潰しと型欠落は失敗の握り込み。明示的に扱い型を付ける。"},
            "q4": {"answer": "a", "rubric": "親→子のマップを一度作り再帰で組む。都度 filter は O(n^2)。"},
        },
        "gap_concepts": ["検索クエリの組み立て", "N+1 とインデックス", "フィルタの共通化"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "検索フィルタ生成: search.ts を読む",
                "summary": "フィルタ組み立ての重複と、検索クエリの責務を把握する。",
                "tech": "",
                "url": None,
                "minutes": 12,
                "priority": "required",
                "source_ref": "src/catalog/search.ts",
            },
            {
                "key": "pg-index",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "PostgreSQL: Indexes",
                "summary": "検索を支える索引の種類と使い所を学ぶ。",
                "tech": "PostgreSQL",
                "url": "https://www.postgresql.org/docs/current/indexes.html",
                "minutes": 20,
                "priority": "recommended",
                "source_ref": None,
            },
        ],
    },
    "inventory": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "stock.py の reserve における在庫チェックと引当の問題はどれ？",
                "code_snippet": _code_snippet("src/inventory/stock.py"),
                "choices": [
                    {"id": "a", "label": "チェックと更新が非アトミックで競合の余地がある"},
                    {"id": "b", "label": "特に問題はない"},
                    {"id": "c", "label": "在庫を誤って増やしている"},
                    {"id": "d", "label": "SKU を無視している"},
                ],
                "difficulty": "L4",
            },
            {
                "id": "q2",
                "kind": "multiple_choice",
                "prompt": "stock.py の reserve を同時実行下でも正しくするにはどうすべき？",
                "code_snippet": _code_snippet("src/inventory/stock.py"),
                "choices": [
                    {"id": "a", "label": "トランザクション＋行ロック、または原子的な条件付き更新で守る"},
                    {"id": "b", "label": "処理前に固定時間 sleep する"},
                    {"id": "c", "label": "特に対策しない"},
                    {"id": "d", "label": "グローバル変数で在庫を管理する"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "reservation.py の reserve_for_order が抱える問題はどれ？",
                "code_snippet": _code_snippet("src/inventory/reservation.py"),
                "choices": [
                    {"id": "a", "label": "途中の明細で失敗しても確保済みが解放されない（部分確保のリーク）"},
                    {"id": "b", "label": "確保数が常に 0 になる"},
                    {"id": "c", "label": "リストを返している点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q4",
                "kind": "multiple_choice",
                "prompt": "warehouse.py の pick_warehouse の倉庫選定に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/inventory/warehouse.py"),
                "choices": [
                    {"id": "a", "label": "在庫の有無を見ず地域一致だけで選び、欠品倉庫を返し得る"},
                    {"id": "b", "label": "地域を見ている点"},
                    {"id": "c", "label": "ループを使っている点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L2",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "read→write が非アトミックだと超過引当が起きうる。"},
            "q2": {"answer": "a", "rubric": "トランザクション境界と行ロック/原子的更新で競合を防ぐ。"},
            "q3": {"answer": "a", "rubric": "全明細を 1 トランザクションにまとめ、失敗時は一括ロールバックする。"},
            "q4": {"answer": "a", "rubric": "在庫と距離/コストを加味して選ぶ。地域一致だけでは欠品倉庫を返し得る。"},
        },
        "gap_concepts": ["在庫引当のトランザクション境界", "競合状態（レースコンディション）", "冪等な引当"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "在庫引当: stock.py を読む",
                "summary": "在庫チェックと更新の原子性、決済との密結合点を把握する。",
                "tech": "",
                "url": None,
                "minutes": 12,
                "priority": "required",
                "source_ref": "src/inventory/stock.py",
            },
            {
                "key": "sa-tx",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "SQLAlchemy: トランザクション",
                "summary": "セッションとトランザクション境界、ロックの扱い。",
                "tech": "SQLAlchemy",
                "url": "https://docs.sqlalchemy.org/en/20/orm/session_transaction.html",
                "minutes": 20,
                "priority": "recommended",
                "source_ref": None,
            },
        ],
    },
    "user": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "profile.py の update_profile に潜む危険はどれ？",
                "code_snippet": _code_snippet("src/user/profile.py"),
                "choices": [
                    {"id": "a", "label": "入力検証なしで全フィールドを上書きする mass assignment"},
                    {"id": "b", "label": "特に問題はない"},
                    {"id": "c", "label": "処理が遅い"},
                    {"id": "d", "label": "ログが多すぎる"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q2",
                "kind": "multiple_select",
                "prompt": "profile.py の update_profile を安全にする対策をすべて選べ。",
                "code_snippet": _code_snippet("src/user/profile.py"),
                "choices": [
                    {"id": "a", "label": "更新可能フィールドのホワイトリスト化"},
                    {"id": "b", "label": "入力バリデーション"},
                    {"id": "c", "label": "本人/権限のチェック"},
                    {"id": "d", "label": "任意のキーをそのまま setattr する"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "address.py の save_address に不足している処理はどれ？",
                "code_snippet": _code_snippet("src/user/address.py"),
                "choices": [
                    {"id": "a", "label": "郵便番号・国コードなど入力値のバリデーション"},
                    {"id": "b", "label": "user_id の設定"},
                    {"id": "c", "label": "コミット"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q4",
                "kind": "multiple_choice",
                "prompt": "Address(**data) のように受け取ったデータをそのままモデルに展開する危険はどれ？",
                "code_snippet": _code_snippet("src/user/address.py"),
                "choices": [
                    {"id": "a", "label": "想定外のフィールドまで設定され得る（mass assignment）"},
                    {"id": "b", "label": "辞書を使っている点"},
                    {"id": "c", "label": "キーワード引数を使っている点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "検証なしの一括上書きは権限昇格・改ざんの温床。"},
            "q2": {"answer": ["a", "b", "c"], "rubric": "ホワイトリスト・検証・認可が対策。無差別 setattr は不可。"},
            "q3": {"answer": "a", "rubric": "住所は形式検証が必須。未検証保存は配送失敗や不正データの原因。"},
            "q4": {"answer": "a", "rubric": "受信データの丸展開は許可フィールドに限定して防ぐ。"},
        },
        "gap_concepts": ["mass assignment 対策", "入力バリデーション", "認可の境界"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "プロフィール更新: profile.py を読む",
                "summary": "更新フィールドの扱いと入力検証・認可の観点を把握する。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "required",
                "source_ref": "src/user/profile.py",
            },
            {
                "key": "owasp-ma",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "OWASP: Mass Assignment 対策",
                "summary": "一括代入の危険と防御パターンを学ぶ。",
                "tech": "Security",
                "url": "https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html",
                "minutes": 15,
                "priority": "recommended",
                "source_ref": None,
            },
        ],
    },
    "shipping": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "shipping.py の create_shipment に欠けている考慮はどれ？",
                "code_snippet": _code_snippet("src/shipping/shipping.py"),
                "choices": [
                    {"id": "a", "label": "キャリア連携失敗時のリトライ / 補償（冪等）"},
                    {"id": "b", "label": "何も欠けていない"},
                    {"id": "c", "label": "ログ出力"},
                    {"id": "d", "label": "型注釈"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q2",
                "kind": "multiple_choice",
                "prompt": "carrier.py の create_label に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/shipping/carrier.py"),
                "choices": [
                    {"id": "a", "label": "タイムアウト未設定でハングし、失敗レスポンスも確認していない"},
                    {"id": "b", "label": "POST を使っている点"},
                    {"id": "c", "label": "JSON を送っている点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "tracking.ts の poll の実装に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/shipping/tracking.ts"),
                "choices": [
                    {"id": "a", "label": "終了条件のない無限ループで、バックオフもなく毎秒 API を叩く"},
                    {"id": "b", "label": "await を使っている点"},
                    {"id": "c", "label": "status を取得している点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q4",
                "kind": "multiple_select",
                "prompt": "外部キャリア API 連携の信頼性を高める対策をすべて選べ。",
                "code_snippet": _code_snippet("src/shipping/carrier.py"),
                "choices": [
                    {"id": "a", "label": "タイムアウトの設定"},
                    {"id": "b", "label": "有限回のリトライ（指数バックオフ）"},
                    {"id": "c", "label": "冪等キーで二重発行を防ぐ"},
                    {"id": "d", "label": "例外を握り潰して無視する"},
                ],
                "difficulty": "L4",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "外部連携は失敗前提。リトライ/補償と冪等性が要る。"},
            "q2": {"answer": "a", "rubric": "タイムアウト設定とレスポンス検証がないと、ハングや KeyError を招く。"},
            "q3": {"answer": "a", "rubric": "配達完了で止まる終了条件と、バックオフ付きのポーリングにする。"},
            "q4": {"answer": ["a", "b", "c"], "rubric": "タイムアウト・有限リトライ・冪等キーが定石。握り潰しは不可。"},
        },
        "gap_concepts": ["外部 API 連携の信頼性", "リトライと冪等性", "配送状態の遷移"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "出荷作成: shipping.py を読む",
                "summary": "キャリア連携の失敗時挙動と、状態遷移の設計を把握する。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "required",
                "source_ref": "src/shipping/shipping.py",
            },
            {
                "key": "httpx",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "httpx: タイムアウトと再試行の考え方",
                "summary": "外部 HTTP 連携の信頼性設計の前提を学ぶ。",
                "tech": "httpx",
                "url": "https://www.python-httpx.org/advanced/",
                "minutes": 15,
                "priority": "recommended",
                "source_ref": None,
            },
        ],
    },
    "notifications": {
        "quiz_questions": [
            {
                "id": "q1",
                "kind": "multiple_choice",
                "prompt": "email.py の send_order_email に潜む不具合はどれ？",
                "code_snippet": _code_snippet("src/notifications/email.py"),
                "choices": [
                    {"id": "a", "label": "テンプレ変数の欠落で KeyError になり得る"},
                    {"id": "b", "label": "特に問題はない"},
                    {"id": "c", "label": "送信が速すぎる"},
                    {"id": "d", "label": "型が厳しすぎる"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q2",
                "kind": "multiple_choice",
                "prompt": "templates.py の render に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/notifications/templates.py"),
                "choices": [
                    {"id": "a", "label": "未知テンプレ名や欠損キーで KeyError になり得る"},
                    {"id": "b", "label": "辞書を使っている点"},
                    {"id": "c", "label": "文字列を返している点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "push.ts の pushAll に潜む問題はどれ？",
                "code_snippet": _code_snippet("src/notifications/push.ts"),
                "choices": [
                    {"id": "a", "label": "直列送信で件数に比例して遅く、失敗時のリトライもない"},
                    {"id": "b", "label": "for-of を使っている点"},
                    {"id": "c", "label": "await を使っている点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q4",
                "kind": "multiple_select",
                "prompt": "通知を確実に届けるための設計をすべて選べ。",
                "code_snippet": _code_snippet("src/notifications/push.ts"),
                "choices": [
                    {"id": "a", "label": "送信の非同期化・キュー投入"},
                    {"id": "b", "label": "失敗時のリトライ"},
                    {"id": "c", "label": "テンプレ変数の検証"},
                    {"id": "d", "label": "全ユーザーへ同期で一斉送信"},
                ],
                "difficulty": "L3",
            },
        ],
        "quiz_answer_key": {
            "q1": {"answer": "a", "rubric": "テンプレ変数の欠落は実行時 KeyError の原因。事前検証が必要。"},
            "q2": {"answer": "a", "rubric": "テンプレ名・変数の存在を検証し、安全なテンプレエンジンで描画する。"},
            "q3": {"answer": "a", "rubric": "並行送信＋失敗リトライにする。直列送信は件数に比例して遅い。"},
            "q4": {"answer": ["a", "b", "c"], "rubric": "非同期化・リトライ・変数検証が有効。同期一斉送信は不可。"},
        },
        "gap_concepts": ["テンプレートの安全な描画", "非同期送信とリトライ", "通知の重複防止"],
        "resources": [
            {
                "key": "code",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "注文メール送信: email.py を読む",
                "summary": "テンプレ描画の落とし穴と、送信の信頼性設計を把握する。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "required",
                "source_ref": "src/notifications/email.py",
            },
            {
                "key": "jinja",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "Jinja2: テンプレート",
                "summary": "安全なテンプレート描画と変数の扱いを学ぶ。",
                "tech": "Jinja2",
                "url": "https://jinja.palletsprojects.com/en/stable/templates/",
                "minutes": 15,
                "priority": "recommended",
                "source_ref": None,
            },
        ],
    },
}


def _feature_quiz(feature_key: str, feature_name: str, member_files: list[str]) -> tuple[list[dict], dict]:
    """Return ``(questions, answer_key)`` for a feature's confirmation quiz.

    Checkout reuses the rich payment-specific quiz, the core EC features have their own curated
    banks (``_FEATURE_CONTENT``), and the long-tail extra features fall back to a generic-but-valid
    three-question set. The fallback attaches the feature's representative file as a code snippet so
    every 理解度チェック shows real code (no "コードスニペットなし") and is takeable end-to-end.
    """
    if feature_key == "checkout":
        return _QUIZ_QUESTIONS, _QUIZ_ANSWER_KEY
    curated = _FEATURE_CONTENT.get(feature_key)
    if curated:
        return curated["quiz_questions"], curated["quiz_answer_key"]
    rep = member_files[0] if member_files else ""
    snippet = _code_snippet(rep) if rep else None
    questions: list[dict] = [
        {
            "id": "q1",
            "kind": "multiple_choice",
            "prompt": f"「{feature_name}」の代表ファイル {rep} を初めて読むとき、意図を最も正しく掴める進め方はどれ？",
            "code_snippet": snippet,
            "choices": [
                {"id": "a", "label": "公開関数の入出力と副作用（DB 書き込み・外部呼び出し）を追う"},
                {"id": "b", "label": "変数名の見た目だけで判断する"},
                {"id": "c", "label": "コメントを読まずに書き換える"},
                {"id": "d", "label": "実行して落ちるまで放置する"},
            ],
            "difficulty": "L2",
        },
        {
            "id": "q2",
            "kind": "multiple_choice",
            "prompt": f"{rep} を安全に変更するため、着手前に最初に確認すべきことはどれ？",
            "code_snippet": snippet,
            "choices": [
                {"id": "a", "label": "既存のテストと関連 PR / ドキュメントを読む"},
                {"id": "b", "label": "まず実装してから挙動を確認する"},
                {"id": "c", "label": "無関係なファイルを先に削除する"},
                {"id": "d", "label": "検証せず本番へ直接デプロイする"},
            ],
            "difficulty": "L2",
        },
        {
            "id": "q3",
            "kind": "multiple_select",
            "prompt": f"「{feature_name}」の理解を深めるうえで有効な行動をすべて選べ。",
            "code_snippet": snippet,
            "choices": [
                {"id": "a", "label": "代表ファイルを読んで責務を把握する"},
                {"id": "b", "label": "依存関係をたどって境界を確認する"},
                {"id": "c", "label": "コミット履歴 / PR で背景を追う"},
                {"id": "d", "label": "理由を確かめずコードを書き換える"},
            ],
            "difficulty": "L3",
        },
    ]
    answer_key = {
        "q1": {"answer": "a", "rubric": "入出力と副作用を追うのがコード理解の基本。"},
        "q2": {"answer": "a", "rubric": "変更前に既存資産（テスト・PR・ドキュメント）を読むのが基本。"},
        "q3": {"answer": ["a", "b", "c"], "rubric": "代表ファイル・依存・履歴の確認が有効。"},
    }
    return questions, answer_key


def _feature_plan(feature_key: str, feature_name: str, member_files: list[str]) -> tuple[list[str], list[dict]]:
    """Return ``(gap_concepts, resources)`` for a feature's learning plan.

    Checkout reuses the curated resources; other features get a code-walkthrough team asset
    (representative file) + an external stack doc so every block has an openable, non-empty plan.
    Resource dicts use the keys documented at ``_PLAN_RESOURCES``.
    """
    if feature_key == "checkout":
        return _PLAN_GAP_CONCEPTS, _PLAN_RESOURCES
    curated = _FEATURE_CONTENT.get(feature_key)
    if curated:
        return curated["gap_concepts"], curated["resources"]
    rep = member_files[0]
    resources: list[dict] = [
        {
            "key": "code",
            "origin": "team",
            "section": "code",
            "kind": "code",
            "title": f"代表ファイルを読む: {rep}",
            "summary": f"{rep} を読み、「{feature_name}」の中核ロジックと責務を把握する。",
            "tech": "",
            "url": None,
            "minutes": 15,
            "priority": "required",
            "source_ref": rep,
        },
        {
            "key": "stack",
            "origin": "external",
            "section": "stack",
            "kind": "docs",
            "title": f"「{feature_name}」に関わる技術の基礎",
            "summary": f"「{feature_name}」で使う技術スタックの一般的な解説で前提知識を補う。",
            "tech": "general",
            "url": "https://developer.mozilla.org/",
            "minutes": 20,
            "priority": "recommended",
            "source_ref": None,
        },
    ]
    return [f"「{feature_name}」全体の理解", "代表ファイルの責務", "依存関係の境界"], resources


# Hand-written, line-anchored walkthroughs for the code-理解 resources referenced by learning plans.
# Each list of steps explains the ACTUAL seeded snippet (identifiers, line ranges, the concrete risk and
# how to fix it) at a senior-review level, so the demo reads like a real code review rather than a
# templated summary. Line numbers match the corresponding ``_DEMO_SNIPPETS`` entry. Files without an
# entry fall back to the generic two-part split in ``_walkthrough_for``.
_WALKTHROUGHS: dict[str, list[dict]] = {
    "src/checkout/payment.py": [
        {
            "start_line": 1,
            "end_line": 3,
            "title": "入口と多重ガード",
            "explanation": (
                "confirm_payment は注文・ユーザーと、キーワード専用の retries を受け取る。2〜3 行目で "
                "order.total > 0 と user.is_active を入れ子の if で確認しており、ここからガード条件がネスト"
                "し始める。ガードを増やすたびに 1 段深くなる構造が、この関数の循環的複雑度が 31 まで跳ね上がる"
                "主因。early-return（ガード節）に直すだけで見通しは大きく良くなる。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 5,
            "title": "在庫引当 → 課金の順序",
            "explanation": (
                "4 行目 reserve_stock で在庫を確保してから 5 行目 charge で課金する。『在庫を押さえてから請求"
                "する』という順序自体は正しい。ただし各ステップの成否をさらに入れ子の if で分岐するため、成功"
                "パスと失敗パスが同じ深いブロックの中で絡み合い、どの条件でどこへ抜けるのかを追いにくい。"
            ),
        },
        {
            "start_line": 6,
            "end_line": 8,
            "title": "確定失敗時の補償（ロールバック）",
            "explanation": (
                "6 行目 mark_paid（注文確定）が失敗すると、7 行目 rollback_charge で課金を取り消し 8 行目で "
                "False を返す。課金済みなのに確定できない不整合を補償する最重要の分岐。ただしここでは在庫の解放"
                "を行っておらず、確定失敗時に在庫が確保されたまま取り残される抜けがある。"
            ),
        },
        {
            "start_line": 9,
            "end_line": 10,
            "title": "課金失敗時の在庫解放",
            "explanation": (
                "9〜10 行目の else は charge が失敗した場合で、release_stock で確保済み在庫を戻す。補償処理が"
                "『charge 失敗』と『mark_paid 失敗』の 2 箇所に分散しているため、どちらがどの後始末をするのかが"
                "読み手に伝わりづらい。補償は 1 か所（例: try/except or finally）へ集約したい。"
            ),
        },
        {
            "start_line": 11,
            "end_line": 11,
            "title": "既定の戻り値に潜む落とし穴",
            "explanation": (
                "最後は無条件で True を返す。このため total<=0 や非アクティブユーザーでガードに弾かれ、何も課金"
                "していないケースでも True（成功）を返してしまう。呼び出し側は成功と誤認し得る。状態ごとに明示的"
                "な戻り値（または例外）を返し、冪等キーで再送を安全にするのが正攻法。"
            ),
        },
    ],
    "src/checkout/cart.py": [
        {
            "start_line": 1,
            "end_line": 1,
            "title": "引当のエントリポイント",
            "explanation": (
                "allocate_inventory はカート内の各明細を走査して在庫を引き当てる。カート全体を 1 つの処理で回す"
                "ため、途中で例外が出たときに『どこまで確保したか』が曖昧になりやすい構造を最初に押さえておく。"
            ),
        },
        {
            "start_line": 2,
            "end_line": 4,
            "title": "数量ガード",
            "explanation": (
                "2〜4 行目で明細をループし、qty<=0 の明細は continue でスキップする。無効数量を弾く定石だが、"
                "この後の在庫状態チェックと合わさってネストが深くなり、複雑度 18 を押し上げている。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 6,
            "title": "在庫状態による分岐",
            "explanation": (
                "5 行目で『予約済み(RESERVED) かつ backorder 不可』を判定し 6 行目で OutOfStock を送出する。"
                "2 つ以上の条件が組み合わさっており、backorder_allowed の意味を知らないと分岐の意図が読み取れない。"
                "条件に名前を付けて（例: needs_immediate_stock）意図を明示すると良い。"
            ),
        },
        {
            "start_line": 7,
            "end_line": 7,
            "title": "引当の実行と部分確保のリーク",
            "explanation": (
                "7 行目 reserve(item) で実際に確保する。ただし後続の明細で OutOfStock を投げると、それ以前に "
                "reserve 済みの明細が解放されないまま関数を抜ける（部分引当のリーク）。全明細を 1 つのトランザク"
                "ション境界にまとめ、いずれか失敗したら一括ロールバックする設計が必要。"
            ),
        },
    ],
    "src/auth/session.py": [
        {
            "start_line": 1,
            "end_line": 3,
            "title": "セッション検証の本体",
            "explanation": (
                "validate_session は token を decode してクレームを取り出し、3 行目で expired でなければその"
                "クレームを、期限切れなら None を返す。呼び出し側は None を見て再認証へ誘導する契約。ここで"
                "重要なのは『期限切れを黙って通さない』こと。expired の判定は信頼できる時刻源で行う。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 6,
            "title": "未使用の旧クッキー検証（dead code）",
            "explanation": (
                "5〜6 行目の _legacy_cookie_check は旧 sid_v1 クッキーを読むが、どこからも呼ばれていない到達不能"
                "コード。残すと『まだ使われている』と誤解され、変更・削除の判断を鈍らせる（＝理解負債の温床）。"
                "参照検索で未使用を確認したうえで安全に削除するのが望ましい。"
            ),
        },
    ],
    "src/catalog/search.ts": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "フィルタ生成の入口",
            "explanation": (
                "buildFilters はクエリ q から Filter 配列を組み立てて返す。空配列 f に条件を push していく素直な"
                "作りで、ここまでは読みやすい。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 6,
            "title": "重複したフィルタ組み立て",
            "explanation": (
                "3〜6 行目は category / minPrice / maxPrice / brand を、それぞれ if で判定して push する『ほぼ"
                "同一形』のブロックが 4 回並ぶ。条件を 1 つ足すたびにこのパターンをコピーする必要があり、片方"
                "だけ直して他を直し忘れる修正漏れの温床になる。"
            ),
        },
        {
            "start_line": 7,
            "end_line": 8,
            "title": "共通化の余地",
            "explanation": (
                "7 行目のコメントどおり、同じ組み立てがリポジトリ内 4 箇所に重複している。フィールド名・演算子・"
                "値の対応表（例: [{key:'category', op:'eq'}, ...]）を用意して map で回す形へ共通化すれば、条件"
                "追加が 1 行で済み重複も消える。テストも 1 か所で担保できる。"
            ),
        },
    ],
    "src/inventory/stock.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "現在庫の読み取り",
            "explanation": (
                "reserve は SKU と数量を受け取り、2 行目で在庫辞書 STOCK から現在の在庫レベルを読む（未登録は 0）。"
                "この『読み取り』が後続の『更新』と別ステップに分かれている点が、以降で問題になる。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 4,
            "title": "在庫チェック",
            "explanation": (
                "3〜4 行目で要求数量が在庫を上回れば OutOfStock を送出する。単体のロジックとしては正しいが、"
                "この判定（read）と後続の減算（write）の間に隙間があることが競合の入り口になる。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 6,
            "title": "非アトミックな引当（レースの核心）",
            "explanation": (
                "5 行目で在庫を減算し 6 行目で Reservation を返す。read（2 行目）と write（5 行目）の間に他の"
                "リクエストが割り込むと、同じ在庫を二重に引き当てて在庫がマイナスになる競合（レースコンディション）"
                "が起きる。トランザクション＋行ロック、または DB の原子的な条件付き更新"
                "（UPDATE stock SET qty = qty - :n WHERE sku = :sku AND qty >= :n）で守る必要がある。"
            ),
        },
    ],
    "src/user/profile.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "更新対象の読み込み",
            "explanation": (
                "update_profile は user_id と patch（更新内容）を受け取り、2 行目で対象ユーザーを読み込む。"
                "ここまでは普通の更新処理。問題は次の一括代入にある。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 4,
            "title": "無検証の一括代入（mass assignment）",
            "explanation": (
                "3〜4 行目で patch の全キーをそのまま setattr している。patch に is_admin や email_verified など"
                "本来クライアントに更新させたくない属性が混じっていても上書きできてしまう、典型的な mass "
                "assignment 脆弱性。更新可能フィールドのホワイトリスト化と入力バリデーションが必須。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 5,
            "title": "永続化と欠けている認可",
            "explanation": (
                "5 行目で保存する。ここへ来る前に『誰が・どのフィールドを』更新してよいかの認可チェックも要る"
                "が、現状は本人性・権限の確認がない。認可 → 検証 → ホワイトリスト適用 → 保存の順に整える。"
            ),
        },
    ],
    "src/shipping/shipping.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "配送キャリアの選定",
            "explanation": (
                "create_shipment は注文の地域に応じてキャリアを選ぶ（2 行目 pick_carrier）。ここは純粋な選定"
                "ロジックで副作用はない。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 3,
            "title": "外部連携（失敗前提が抜けている）",
            "explanation": (
                "3 行目 carrier.create_label は外部 API 呼び出しであり、失敗・タイムアウトが前提。にもかかわらず"
                "リトライも補償もなく、例外が出れば注文だけ進んで出荷ラベルが無い不整合になり得る。外部境界は"
                "つねに『落ちる』前提で設計する。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 5,
            "title": "結果の反映と冪等性",
            "explanation": (
                "4〜5 行目で tracking 番号を注文に書き戻して返す。外部連携はタイムアウト設定・有限リトライ"
                "（指数バックオフ）・冪等キー（同じ注文で二重にラベル発行しない）をセットで設計するのが定石。"
            ),
        },
    ],
    "src/notifications/email.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "テンプレートの取得",
            "explanation": (
                "send_order_email は注文からテンプレート order_confirm を取り出す（2 行目）。ここは辞書参照で、"
                "テンプレ名が固定なら安全。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 3,
            "title": "危険なテンプレ描画",
            "explanation": (
                "3 行目で order.__dict__ を丸ごと展開して format している。テンプレートが参照する変数が注文"
                "オブジェクトに無ければ実行時 KeyError で送信そのものが失敗する。__dict__ の丸投げは意図しない"
                "属性の露出にもつながる。必要な変数だけを明示的に渡し、描画前に存在を検証すべき。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 4,
            "title": "送信の信頼性",
            "explanation": (
                "4 行目で SMTP 送信する。通知は失敗前提でキュー投入＋リトライにし、テンプレ変数の欠落は描画前に"
                "検出する設計が望ましい。同期送信は遅延と失敗連鎖の原因になる。"
            ),
        },
    ],
}


def _walkthrough_for(source_ref: str) -> tuple[str, list[dict]]:
    """Return ``(source_content, walkthrough steps)`` for a demo code resource.

    Curated files (``_WALKTHROUGHS``) get hand-written, line-anchored steps that explain the actual
    seeded source concretely; any other file falls back to a generic two-part split. Either way the
    code-理解 walkthrough renders inline without fetching source from GitHub (demo is GitHub-less).
    """
    content = _DEMO_SNIPPETS.get(source_ref) or _snippet_for(source_ref, "other")
    curated = _WALKTHROUGHS.get(source_ref)
    if curated:
        return content, curated
    total = max(1, len(content.rstrip("\n").split("\n")))
    if total <= 2:
        return content, [
            {
                "start_line": 1,
                "end_line": total,
                "title": "全体を読む",
                "explanation": "このコード断片の全体に目を通し、何をしている処理かを把握する。",
            }
        ]
    mid = total // 2
    return content, [
        {
            "start_line": 1,
            "end_line": mid,
            "title": "前半: 入力と前提",
            "explanation": "何を受け取り、どんな前提・分岐から処理が始まるかを読む。",
        },
        {
            "start_line": mid + 1,
            "end_line": total,
            "title": "後半: 中核処理と副作用",
            "explanation": "中核処理と副作用（DB 書き込み・例外・状態遷移）の流れを追う。理解負債が集まりやすい。",
        },
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
    elif isinstance(project, Project) and project.name != DEMO_PROJECT_NAME:
        # 既存行でも表示名の変更（例: "sample project" → "EC ストア"）は反映する。
        project.name = DEMO_PROJECT_NAME
        session.add(project)

    await session.commit()
    # Re-fetch so callers get attached, refreshed instances.
    org = await _get(session, Org, org_id)
    project = await _get(session, Project, project_id)
    if not isinstance(org, Org) or not isinstance(project, Project):  # pragma: no cover - just inserted/loaded
        raise RuntimeError("demo org/project not found after upsert")
    return org, project


async def _ensure_extra_projects(session: AsyncSession, org: Org, user_id: uuid.UUID) -> None:
    """Create metadata-only extra projects in the demo org (idempotent).

    They have no analysis rows — their purpose is to give the sidebar several projects to
    organize into starred / sections (client-side feature). Deterministic uuid5 ids keep re-runs stable.
    """
    for slug, name in _EXTRA_PROJECTS:
        project_id = _u("project", DEMO_ORG_SLUG, slug)
        if await _get(session, Project, project_id) is None:
            session.add(
                Project(
                    id=project_id,
                    org_id=org.id,
                    name=name,
                    slug=slug,
                    repo_owner=DEMO_REPO_OWNER,
                    repo_name=slug,
                    repo_full_name=f"{DEMO_REPO_OWNER}/{slug}",
                    default_branch=DEMO_DEFAULT_BRANCH,
                    repo_private=False,
                    github_repo_id=None,
                    created_by=user_id,
                )
            )
    await session.commit()


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
                    code_snippet=_DEMO_SNIPPETS.get(file_path) or _snippet_for(file_path, dtype),
                    code_debt_score=score,
                    knowledge_coverage=kc_by_path.get(file_path, 0.0),
                    ai_generation_prob=ai_prob,
                    estimated_repay_hours=repay,
                    metrics={"cyclomatic_complexity": int(score * 40)},
                    created_at=now,
                )
            )

    # Every other analysed file gets one synthesized finding so the Overview scatter plots it at its
    # real code_debt_score. build_overview reads code_debt_score from CodeDebt rows only — files with
    # no row collapse to 0.0 and pile on the clean top edge. Severity/type derive from the score; the
    # curated findings above keep their richer notes.
    curated = {fp for fp, *_ in _CODE_DEBTS}
    _types = ("complexity", "duplicate", "dead", "other")
    _notes = {
        "complexity": "条件分岐が多く入れ子も深いため、処理の流れを追いづらくなっています。",
        "duplicate": "よく似た処理が複数箇所に重複していて、修正漏れが起きやすい状態です。",
        "dead": "どこからも呼ばれていない関数や到達しない分岐が残っています。",
        "other": "型の情報が不足し例外も握り潰されているため、不具合に気づきにくい状態です。",
    }
    for idx, (file_path, _language, _loc, _kc, score) in enumerate(_FILES):
        if file_path in curated:
            continue
        dtype = _types[idx % len(_types)]
        severity = "critical" if score >= 0.7 else "high" if score >= 0.5 else "medium" if score >= 0.3 else "low"
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
                    archaeology_notes=_notes[dtype],
                    code_snippet=_DEMO_SNIPPETS.get(file_path) or _snippet_for(file_path, dtype),
                    code_debt_score=score,
                    knowledge_coverage=kc_by_path.get(file_path, 0.0),
                    ai_generation_prob=round(score * 0.6, 2),
                    estimated_repay_hours=round(score * 4, 1),
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
                    code_snippet=_DEMO_SNIPPETS.get(file_path) or _snippet_for(file_path, "other"),
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


async def _ensure_quizzes(session: AsyncSession, project: Project, dev_id: uuid.UUID) -> None:
    """Seed one UNANSWERED feature-scoped quiz per feature (idempotent).

    Each quiz is left ``not_started`` with ``granularity="feature"`` so build_knowledge_units
    surfaces a takeable 理解度チェック for EVERY block (matched by feature_id + developer_id).
    """
    fc_run = _run_id(JobType.FEATURE_CLUSTERING)
    for feature_key, feature_name, _description, paths in _FEATURES:
        feature_id = _u("feature", fc_run, feature_key)
        row_id = _u("quiz_session", project.id, dev_id, feature_key)
        if await _get(session, QuizSession, row_id) is None:
            questions, answer_key = _feature_quiz(feature_key, feature_name, paths)
            session.add(
                QuizSession(
                    id=row_id,
                    project_id=project.id,
                    developer_id=dev_id,
                    file_path=paths[0],
                    repo_full_name=DEMO_REPO_FULL_NAME,
                    granularity="feature",
                    feature_id=feature_id,
                    is_baseline=True,
                    status="not_started",
                    questions=questions,
                    answer_key=answer_key,
                    source_kc=0.18,
                )
            )
    await session.commit()


async def _ensure_learning_plans(session: AsyncSession, project: Project, dev_id: uuid.UUID) -> None:
    """Seed a LearningPlan (resources + ordered steps) for EVERY feature (idempotent).

    Team assets are inserted before external ones so each plan reads "チーム資産が上段" — the
    knowledge-debt repayment loop's payoff. Resource ids are namespaced per feature so the same
    generic resource key reused across features does not collide.
    """
    fc_run = _run_id(JobType.FEATURE_CLUSTERING)
    for feature_key, feature_name, _description, paths in _FEATURES:
        feature_id = _u("feature", fc_run, feature_key)
        plan_id = _u("learning_plan", project.id, dev_id, feature_key)
        gap_concepts, resources = _feature_plan(feature_key, feature_name, paths)

        # Resources first (steps FK them).
        resource_ids: dict[str, uuid.UUID] = {}
        for res in resources:
            key = res["key"]
            res_id = _u("learning_resource", project.id, feature_key, key)
            resource_ids[key] = res_id
            if await _get(session, LearningResource, res_id) is None:
                source_ref = res.get("source_ref")
                # Code-section resources get a seeded walkthrough + inline source so the code-理解
                # ウォークスルー opens without fetching from GitHub (demo is GitHub-less — issue 069).
                walkthrough: list[dict] = []
                origin_meta: dict = {}
                if res["section"] == "code" and source_ref:
                    content, walkthrough = _walkthrough_for(source_ref)
                    origin_meta = {"demo_source": content}
                session.add(
                    LearningResource(
                        id=res_id,
                        project_id=project.id,
                        origin=res["origin"],
                        section=res["section"],
                        kind=res["kind"],
                        title=res["title"],
                        summary=res["summary"],
                        tech=res["tech"],
                        source_ref=source_ref,
                        url=res["url"],
                        estimated_minutes=res["minutes"],
                        priority=res["priority"],
                        walkthrough=walkthrough,
                        origin_meta=origin_meta,
                    )
                )

        if await _get(session, LearningPlan, plan_id) is None:
            total = sum(r["minutes"] for r in resources)
            session.add(
                LearningPlan(
                    id=plan_id,
                    project_id=project.id,
                    developer_id=dev_id,
                    feature_id=feature_id,
                    gap_concepts=gap_concepts,
                    estimated_total_minutes=total,
                )
            )

        for order, res in enumerate(resources):
            step_id = _u("learning_step", plan_id, order)
            if await _get(session, LearningStep, step_id) is None:
                session.add(
                    LearningStep(
                        id=step_id,
                        plan_id=plan_id,
                        order=order,
                        completed=False,
                        resource_id=resource_ids[res["key"]],
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
    org, project = await _ensure_org_and_project(session, user_id)
    await _ensure_extra_projects(session, org, user_id)
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
    await _ensure_quizzes(session, project, user_id)
    await _ensure_learning_plans(session, project, user_id)
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

    # Learning plans + steps + resources (project-scoped; steps deleted per feature plan).
    for feature_key, *_rest in _FEATURES:
        plan_id = _u("learning_plan", project_id, dev_id, feature_key)
        await session.execute(delete(LearningStep).where(col(LearningStep.plan_id) == plan_id))
    await session.execute(delete(LearningPlan).where(col(LearningPlan.project_id) == project_id))
    await session.execute(delete(LearningResource).where(col(LearningResource.project_id) == project_id))

    # Quiz sessions (project-scoped). Answers/results FK the sessions, so clear them first
    # (a guest may have taken a quiz, leaving quiz_answers/quiz_results rows).
    session_ids = (
        (await session.execute(select(QuizSession.id).where(col(QuizSession.project_id) == project_id))).scalars().all()
    )
    if session_ids:
        await session.execute(delete(QuizAnswer).where(col(QuizAnswer.session_id).in_(session_ids)))
        await session.execute(delete(QuizResult).where(col(QuizResult.session_id).in_(session_ids)))
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
