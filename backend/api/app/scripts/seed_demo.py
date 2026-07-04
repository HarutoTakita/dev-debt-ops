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
import logging
import posixpath
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as app_db
from app.core.config import settings
from app.models.app_metadata import AppMetadata
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
    ("src/auth/session.py", "Python", 188, 0.27, 0.72),  # 知識ホットスポット かつ 高リスク（P0）
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
    """Varied but deterministic KC so map colors are a mix (理解済み/部分/未理解/未着手).

    KC=0（未着手）はごく少数（~3%）に絞る。多いと散布図の左端に点が一直線に並んで見栄えが悪いため。
    残りは 0.06〜0.95 に広く分布させ、横軸(理解度)方向にしっかりバラけるようにする。
    """
    if _det01("kc", path) < 0.03:
        return 0.0  # ~3% だけ未着手（unexplored / グレー）— 象徴的に残す
    return round(0.06 + _det01("kcv", path) * 0.89, 2)  # 0.06〜0.95 に分布


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
        "complexity",
        "high",
        0.72,
        0.28,
        5.0,
        (
            "認証の中核。トークンの検証・失効・スライディング更新の分岐が入り組み、旧セッション経路の"
            "デッドコードも残存。理解が薄いまま変更するとログイン不能や失効漏れにつながる高リスク箇所です。"
        ),
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
        "                        rollback_charge(order)  # ネストが深く循環的複雑度が高い\n"
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
        "            raise OutOfStock(item.sku)  # 分岐が多く複雑度が高い\n"
        "        reserve(item)\n"
    ),
    "src/auth/session.py": (
        "SESSION_TTL = timedelta(hours=2)      # アクセスセッションの有効期間\n"
        "REFRESH_TTL = timedelta(days=14)      # 「ログイン状態を保持」の更新期間\n"
        "\n"
        "\n"
        "def create_session(user, response):\n"
        '    """ログイン成功時にセッションを発行し、Cookie に載せる。"""\n'
        "    now = utcnow()\n"
        "    claims = {\n"
        '        "sub": user.id,\n'
        '        "epoch": user.token_epoch,    # 失効の世代番号（後述）\n'
        '        "iat": now,\n'
        '        "exp": now + SESSION_TTL,\n'
        "    }\n"
        "    token = jwt.encode(claims)\n"
        '    response.set_cookie("sid", token, httponly=True, secure=True, samesite="Lax")\n'
        '    response.set_cookie("csrf", new_csrf_token(), samesite="Lax")\n'
        "    return token\n"
        "\n"
        "\n"
        "def validate_session(request):\n"
        '    """セッション Cookie を検証し、有効ならユーザーを返す。"""\n'
        '    token = request.cookies.get("sid")\n'
        "    if not token:\n"
        "        return None\n"
        "    claims = jwt.decode(token)         # 署名を検証（改ざん検出）\n"
        '    if claims is None or claims["exp"] < utcnow():\n'
        "        return None                    # 改ざん・期限切れは無効 → 再認証\n"
        '    user = load_user(claims["sub"])\n'
        '    if user is None or user.token_epoch != claims["epoch"]:\n'
        "        return None                    # 世代不一致は失効済み\n"
        "    return user\n"
        "\n"
        "\n"
        "def refresh_session(request, response):\n"
        '    """期限が近いセッションを再ログインなしで延長（スライディング更新）。"""\n'
        "    user = validate_session(request)\n"
        "    if user is None:\n"
        "        return None\n"
        "    return create_session(user, response)  # 新しい exp で再発行＝ローテーション\n"
        "\n"
        "\n"
        "def revoke_all_sessions(user):\n"
        '    """全端末ログアウト。token_epoch を進めて既存トークンを一括失効。"""\n'
        "    user.token_epoch += 1\n"
        "    save_user(user)\n"
        "\n"
        "\n"
        "def check_csrf(request):\n"
        '    """状態変更の前に Cookie とヘッダの CSRF トークン一致を確認（二重送信）。"""\n'
        '    return request.cookies.get("csrf") == request.headers.get("X-CSRF-Token")\n'
        "\n"
        "\n"
        "def _legacy_cookie_check(request):     # どこからも呼ばれない未到達パス（dead）\n"
        '    return request.cookies.get("sid_v1")  # 旧 v1 形式。移行後の削除漏れ\n'
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
        "def build_authorize_url(redirect_uri):\n"
        '    """OAuth 認可画面へ送る URL を組み立てる。"""\n'
        "    state = new_state()        # 本来はセッションに保存し、callback で照合する\n"
        '    return f"{AUTHORIZE}?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&state={state}"\n'
        "\n"
        "\n"
        "def handle_callback(request):\n"
        '    """認可サーバからのコールバックを受け、ログイン/アカウント作成する。"""\n'
        '    code = request.args["code"]\n'
        "    token = exchange_code(code)   # state を検証しておらず CSRF の余地\n"
        "    profile = fetch_profile(token)\n"
        "    return login_or_create(profile.email)  # メール検証前に連携 → なりすましの恐れ\n"
    ),
    "src/auth/password.py": (
        "import hashlib\n"
        "\n"
        "\n"
        "def hash_password(raw):\n"
        '    """パスワードをハッシュ化して保存用の文字列を返す。"""\n'
        "    return hashlib.md5(raw.encode()).hexdigest()  # ソルトなし・高速ハッシュで総当たりに弱い\n"
        "\n"
        "\n"
        "def verify_password(raw, stored):\n"
        '    """入力パスワードのハッシュが保存値と一致するか検証する。"""\n'
        "    return hash_password(raw) == stored  # 短絡比較でタイミング攻撃に弱い\n"
        "\n"
        "\n"
        "def needs_rehash(stored):\n"
        '    """保存済みハッシュが旧形式(32桁hex=MD5)なら作り直しが必要と判断する。"""\n'
        "    return len(stored) == 32  # 次回ログイン時に安全な方式へ移行したい（未配線）\n"
    ),
    "src/auth/jwt.py": (
        "import json\n"
        "from base64 import urlsafe_b64decode as b64decode\n"
        "\n"
        "\n"
        "def decode_token(token):\n"
        '    """トークンを分解し、ペイロード(クレーム)を取り出す。"""\n'
        '    header, payload, sig = token.split(".")   # ヘッダ.ペイロード.署名 に分解\n'
        "    claims = json.loads(b64decode(_pad(payload)))\n"
        "    return claims  # 署名(sig) も exp も検証せず → 改ざん・期限切れを見逃す\n"
        "\n"
        "\n"
        "def _pad(segment):\n"
        '    """base64url のパディング(=)を補完する補助関数。"""\n'
        '    return segment + "=" * (-len(segment) % 4)\n'
        "\n"
        "\n"
        "def encode(claims):\n"
        '    """クレームを署名付きトークンにして発行する。"""\n'
        "    return sign(_b64(claims))  # decode 側でこの署名を検証すべき\n"
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
                "prompt": (
                    "create_session が sid Cookie に付ける属性の組み合わせとして、"
                    "XSS・盗聴・CSRF の緩和に最も適切なのはどれ？"
                ),
                "code_snippet": _code_snippet("src/auth/session.py"),
                "choices": [
                    {"id": "a", "label": "httponly=True, secure=True, samesite=Lax"},
                    {"id": "b", "label": "属性なし（デフォルトのまま）"},
                    {"id": "c", "label": "httponly=False にして JS から読めるようにする"},
                    {"id": "d", "label": "有効期限を無期限にする"},
                ],
                "difficulty": "L1",
            },
            {
                "id": "q2",
                "kind": "multiple_select",
                "prompt": (
                    "validate_session が None を返す（＝無効と判断する）のはどのケース？"
                    "該当するものをすべて選んでください。"
                ),
                "code_snippet": _code_snippet("src/auth/session.py"),
                "choices": [
                    {"id": "a", "label": "sid Cookie が存在しない"},
                    {"id": "b", "label": "署名が検証できない（改ざん）"},
                    {"id": "c", "label": "exp を過ぎている（期限切れ）"},
                    {"id": "d", "label": "トークンの epoch がユーザーの token_epoch と一致しない"},
                ],
                "difficulty": "L2",
            },
            {
                "id": "q3",
                "kind": "multiple_choice",
                "prompt": "refresh_session の「スライディング更新」の説明として正しいのはどれ？",
                "code_snippet": _code_snippet("src/auth/session.py"),
                "choices": [
                    {
                        "id": "a",
                        "label": "有効なセッションを新しい exp で再発行し、再ログインなしに延長する（ローテーション）",
                    },
                    {"id": "b", "label": "期限切れでも無条件に延長する"},
                    {"id": "c", "label": "パスワードを再入力させてから延長する"},
                    {"id": "d", "label": "全ユーザーのセッションをまとめて延長する"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q4",
                "kind": "multiple_choice",
                "prompt": "revoke_all_sessions は user.token_epoch を +1 するだけです。これで何が実現できる？",
                "code_snippet": _code_snippet("src/auth/session.py"),
                "choices": [
                    {"id": "a", "label": "発行済みの全トークンが世代チェックに外れ、全端末で即時ログアウトになる"},
                    {"id": "b", "label": "次回ログイン時のみ影響し、既存セッションはそのまま"},
                    {"id": "c", "label": "特定の 1 端末だけログアウトさせる"},
                    {"id": "d", "label": "パスワードがリセットされる"},
                ],
                "difficulty": "L3",
            },
            {
                "id": "q5",
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
                "id": "q6",
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
                "id": "q7",
                "kind": "multiple_choice",
                "prompt": "oauth.py の handle_callback に潜むセキュリティ上の問題はどれ？",
                "code_snippet": _code_snippet("src/auth/oauth.py"),
                "choices": [
                    {"id": "a", "label": "state を検証しておらず CSRF、さらにメール検証前に連携している"},
                    {"id": "b", "label": "認可コードを使っている点"},
                    {"id": "c", "label": "プロフィールを取得している点"},
                    {"id": "d", "label": "問題はない"},
                ],
                "difficulty": "L4",
            },
        ],
        "quiz_answer_key": {
            "q1": {
                "answer": "a",
                "rubric": "httponly は XSS でのトークン窃取、secure は平文送信、samesite は CSRF を緩和する。",
            },
            "q2": {
                "answer": "a,b,c,d",
                "rubric": "無し・改ざん・期限切れ・世代不一致のいずれか一つでも無効。4 条件すべてが該当。",
            },
            "q3": {
                "answer": "a",
                "rubric": "有効なセッションを新 exp で再発行して延長するのがスライディング更新＝ローテーション。",
            },
            "q4": {
                "answer": "a",
                "rubric": (
                    "token_epoch を進めると、発行済みトークンが validate_session の世代チェックで弾かれ即時失効する。"
                ),
            },
            "q5": {"answer": "a", "rubric": "ソルト付きの遅いハッシュ（bcrypt/argon2）が定石。MD5 は不可。"},
            "q6": {"answer": "a", "rubric": "署名と exp を検証しないと改ざん・期限切れトークンを受理してしまう。"},
            "q7": {
                "answer": "a",
                "rubric": "state 検証で CSRF を防ぎ、メール検証済みか確認してから連携するのが正解。",
            },
        },
        "gap_concepts": [
            "セッション発行と Cookie の安全属性",
            "セッションの検証と失効（世代方式）",
            "スライディング更新とローテーション",
            "CSRF 二重送信",
            "パスワードハッシュと JWT 検証",
        ],
        "resources": [
            {
                "key": "code_session",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "セッション管理: session.py を読む",
                "summary": "発行・検証・スライディング更新・全端末失効・CSRF まで、認証の中核を行ごとに読み解く。",
                "tech": "",
                "url": None,
                "minutes": 15,
                "priority": "required",
                "source_ref": "src/auth/session.py",
            },
            {
                "key": "code_oauth",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "OAuth ログイン: oauth.py を読む",
                "summary": "認可 URL の組み立てと state、コールバックでのトークン交換・アカウント連携の流れを追う。",
                "tech": "",
                "url": None,
                "minutes": 12,
                "priority": "required",
                "source_ref": "src/auth/oauth.py",
            },
            {
                "key": "code_jwt",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "トークン: jwt.py を読む",
                "summary": "JWT の分解・デコードと、署名/有効期限の検証がどこで行われるべきかを理解する。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "recommended",
                "source_ref": "src/auth/jwt.py",
            },
            {
                "key": "code_password",
                "origin": "team",
                "section": "code",
                "kind": "code",
                "title": "資格情報: password.py を読む",
                "summary": "パスワードのハッシュ化・照合・旧形式からの移行判定の流れを読み解く。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "recommended",
                "source_ref": "src/auth/password.py",
            },
            {
                "key": "adr_expiry",
                "origin": "team",
                "section": "code",
                "kind": "adr",
                "title": "ADR: セッション有効期限と token_epoch による一括失効",
                "summary": "なぜ 2 時間 + 14 日の二段構えなのか、なぜ世代番号で失効させるのか。設計判断の背景。",
                "tech": "",
                "url": None,
                "minutes": 10,
                "priority": "required",
                "source_ref": None,
            },
            {
                "key": "owasp_session",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "OWASP セッション管理チートシート",
                "summary": "セッション ID の発行・失効・固定化対策の実務ベストプラクティス。",
                "tech": "Security",
                "url": "https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html",
                "minutes": 20,
                "priority": "recommended",
                "source_ref": None,
            },
            {
                "key": "cookies",
                "origin": "external",
                "section": "stack",
                "kind": "docs",
                "title": "Set-Cookie と SameSite（MDN）",
                "summary": "HttpOnly / Secure / SameSite の意味と CSRF・XSS への効き方。",
                "tech": "HTTP Cookie",
                "url": "https://developer.mozilla.org/ja/docs/Web/HTTP/Headers/Set-Cookie",
                "minutes": 12,
                "priority": "recommended",
                "source_ref": None,
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
# 学習プランの解説は「レビュー（何が問題か・どう直すか）」ではなく、実装されている内容が **どんな仕組み・
# どんな意図で・どんな処理を** しているのかを解説する役割。各 step は実際のスニペット（識別子・行範囲）に沿って
# 挙動と目的を説明する。行番号は対応する ``_DEMO_SNIPPETS`` に一致。未登録ファイルは ``_walkthrough_for`` の
# 汎用 2 分割にフォールバックする。
_WALKTHROUGHS: dict[str, list[dict]] = {
    "src/checkout/payment.py": [
        {
            "start_line": 1,
            "end_line": 3,
            "title": "決済確定の入口と前提条件",
            "explanation": (
                "confirm_payment は注文とユーザーを受け取り、決済を確定する関数です。2〜3 行目ではまず "
                "『金額が正であること（order.total > 0）』『ユーザーが有効であること（user.is_active）』を確認し、"
                "この前提を満たしたときだけ後続の処理に進みます。無効な決済を最初に取り除くための入口チェックです。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 5,
            "title": "在庫の確保 → 課金",
            "explanation": (
                "4 行目 reserve_stock で購入分の在庫を先に確保し、5 行目 charge でユーザーのカードに課金します。"
                "『在庫を押さえてから請求する』というこの順序が決済フローの基本で、支払ったのに在庫が無いという"
                "事態を防ぎます。"
            ),
        },
        {
            "start_line": 6,
            "end_line": 8,
            "title": "注文の確定と失敗時の巻き戻し",
            "explanation": (
                "課金に成功したら 6 行目 mark_paid で注文を『支払い済み』に確定します。もし確定に失敗した場合は "
                "7 行目 rollback_charge で先ほどの課金を取り消し、8 行目で False を返します。課金の実態と注文の"
                "状態を食い違わせないための後始末（補償）処理です。"
            ),
        },
        {
            "start_line": 9,
            "end_line": 10,
            "title": "課金できなかった場合の在庫解放",
            "explanation": (
                "5 行目の課金が失敗したときは 9〜10 行目の else に入り、release_stock で先に確保した在庫を戻します。"
                "支払われないまま在庫だけが押さえられた状態を残さないようにする処理です。"
            ),
        },
        {
            "start_line": 11,
            "end_line": 11,
            "title": "処理の完了を返す",
            "explanation": (
                "一連の処理を終えると 11 行目で True を返し、呼び出し側に決済フローが完了したことを伝えます。"
            ),
        },
    ],
    "src/checkout/cart.py": [
        {
            "start_line": 1,
            "end_line": 1,
            "title": "在庫引当の入口",
            "explanation": (
                "allocate_inventory は、カートに入った各商品について在庫を引き当てる処理です。注文を確定する前に、"
                "購入したい数量ぶんの在庫を確保しておく役割を担います。"
            ),
        },
        {
            "start_line": 2,
            "end_line": 4,
            "title": "対象明細の絞り込み",
            "explanation": (
                "2〜4 行目でカート内の明細を 1 件ずつ処理します。数量が 0 以下の明細は continue でスキップし、"
                "実際に在庫確保が必要な明細だけを対象にします。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 6,
            "title": "在庫状況の判定",
            "explanation": (
                "5 行目で『すでに予約済み(RESERVED) で、かつ取り寄せ(backorder) も許可されていない』商品かどうかを"
                "判定します。該当する場合は 6 行目で OutOfStock を送出し、在庫切れであることを呼び出し側に知らせます。"
            ),
        },
        {
            "start_line": 7,
            "end_line": 7,
            "title": "在庫の確保",
            "explanation": (
                "条件を満たした明細について、7 行目 reserve で在庫を確保します。ここまでで、カート内の購入可能な"
                "商品ぶんの在庫が押さえられます。"
            ),
        },
    ],
    "src/auth/session.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "セッションの有効期間を決める定数",
            "explanation": (
                "SESSION_TTL はログイン後のアクセスセッションが有効な時間（ここでは 2 時間）、REFRESH_TTL は"
                "「ログイン状態を保持」で再ログインなしに延長できる期間（14 日）です。この 2 つの期間設計が、"
                "利便性（すぐ切れない）と安全性（盗まれても短時間で無効化）のバランスを決めています。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 17,
            "title": "create_session — セッションの発行と Cookie 設定",
            "explanation": (
                "ログイン成功時に呼ばれ、ユーザー ID(sub)・失効世代(epoch)・発行時刻(iat)・有効期限(exp) を"
                "クレームに詰めて JWT を署名発行します(14 行目)。15〜16 行目では sid（セッション本体）と csrf "
                "トークンを Cookie に載せ、httponly（JS から読めない=XSS 対策）・secure（HTTPS のみ）・"
                "samesite=Lax（別サイトからの送信を抑制=CSRF 緩和）を付けて安全に配布します。"
            ),
        },
        {
            "start_line": 20,
            "end_line": 31,
            "title": "validate_session — 署名・期限・世代の 3 段検証",
            "explanation": (
                "リクエストの sid Cookie を取り出し(22 行目)、jwt.decode で署名を検証して改ざんを検出します"
                "(25 行目)。26 行目で有効期限(exp)を確認し、期限切れや改ざん時は None を返して再認証へ導きます。"
                "さらに 29 行目で、トークン内の epoch がユーザーの現在の token_epoch と一致するかを確認します。"
                "この 3 段（署名・期限・世代）をすべて通ったときだけユーザーを返すのが、この関数の要です。"
            ),
        },
        {
            "start_line": 34,
            "end_line": 39,
            "title": "refresh_session — スライディング更新（ローテーション）",
            "explanation": (
                "まだ有効なセッションを、期限が近づいたら再ログインなしで延長する処理です。validate_session で"
                "現在のセッションが有効なことを確かめてから(36 行目)、create_session を呼んで新しい exp の"
                "トークンを再発行します(39 行目)。古いトークンを新しいものへ差し替える『ローテーション』であり、"
                "長時間ログインを保ちつつ、トークンを定期的に入れ替えて漏洩リスクを下げます。"
            ),
        },
        {
            "start_line": 42,
            "end_line": 45,
            "title": "revoke_all_sessions — 全端末の一括失効",
            "explanation": (
                "『すべての端末からログアウト』やパスワード変更時に呼ばれます。ユーザーの token_epoch を +1 する"
                "だけで(44 行目)、既に発行済みの全トークンは validate_session の世代チェック(29 行目)に引っかかり、"
                "その瞬間から無効になります。トークンを 1 件ずつ探して消す必要がない、軽量な一括失効の仕組みです。"
            ),
        },
        {
            "start_line": 48,
            "end_line": 50,
            "title": "check_csrf — 二重送信による CSRF 対策",
            "explanation": (
                "注文確定など『状態を変える操作』の前に呼び、Cookie 側の csrf トークンとリクエストヘッダの "
                "X-CSRF-Token が一致するかを確認します。別サイトから勝手に送られたリクエストはヘッダを付けられない"
                "ため一致せず、なりすまし送信（CSRF）を防げます。"
            ),
        },
        {
            "start_line": 53,
            "end_line": 54,
            "title": "_legacy_cookie_check — 未使用の旧経路（dead code）",
            "explanation": (
                "以前 sid_v1 Cookie でセッションを判定していた頃の名残で、現在はどこからも呼ばれていません"
                "（到達しないコード）。移行後に削除し忘れているもので、読む人を惑わせるため整理の候補です。"
            ),
        },
    ],
    "src/auth/oauth.py": [
        {
            "start_line": 1,
            "end_line": 4,
            "title": "build_authorize_url — 認可画面への送り出し",
            "explanation": (
                "OAuth ログインの入口です。new_state() で毎回ランダムな state を作り(3 行目)、client_id・"
                "redirect_uri とともに認可 URL に載せて外部の認可サーバへ利用者を送ります(4 行目)。この state は"
                "『あとで戻ってきたリクエストが自分が始めたものか』を照合するための合言葉で、本来はセッションに"
                "保存しておき、コールバックで突き合わせます。"
            ),
        },
        {
            "start_line": 7,
            "end_line": 12,
            "title": "handle_callback — コールバックの受け取りとログイン",
            "explanation": (
                "認可サーバから戻ってきたリクエストを処理します。認可コードを取り出し(9 行目)、トークンと交換して"
                "(10 行目)、プロフィールを取得し(11 行目)、メールアドレスでログイン/アカウント作成します(12 行目)。"
                "ここでは送り出し時の state を照合していないため CSRF の余地があり、メール検証前に連携している点も"
                "なりすまし登録につながり得る、認証フローの要注意箇所です。"
            ),
        },
    ],
    "src/auth/password.py": [
        {
            "start_line": 4,
            "end_line": 6,
            "title": "hash_password — 保存用ハッシュの生成",
            "explanation": (
                "受け取った生パスワードをハッシュ化し、DB 保存用の文字列にして返します。生パスワードをそのまま"
                "保存しないための処理ですが、ここでは MD5 を使っており、ソルトも無いため総当たりやレインボー"
                "テーブルに弱い実装になっています（本来は bcrypt/argon2 などの遅いハッシュが定石）。"
            ),
        },
        {
            "start_line": 9,
            "end_line": 11,
            "title": "verify_password — ログイン時の照合",
            "explanation": (
                "ログイン時に、入力パスワードを同じ方式でハッシュ化し、保存値と一致するかを確認します。一致すれば"
                "本人とみなします。== による短絡比較は、厳密にはタイミング攻撃に弱い点も知っておきたいところです。"
            ),
        },
        {
            "start_line": 14,
            "end_line": 16,
            "title": "needs_rehash — 旧形式ハッシュの移行判定",
            "explanation": (
                "保存済みハッシュが旧形式（32 桁 hex = MD5）かどうかを長さで判定します。ログイン成功時に安全な"
                "方式へ静かに作り直す『段階的移行』のための入口ですが、この判定を使う配線はまだ未実装です。"
            ),
        },
    ],
    "src/auth/jwt.py": [
        {
            "start_line": 5,
            "end_line": 9,
            "title": "decode_token — トークンの分解とクレーム取得",
            "explanation": (
                "JWT は『ヘッダ.ペイロード.署名』の 3 部構成です。7 行目で分解し、8 行目でペイロードを base64url "
                "デコードして JSON のクレーム（sub や exp など）を取り出します。ただし取り出した署名(sig)を検証"
                "しておらず、有効期限(exp)も見ていないため、改ざんや期限切れのトークンを受理してしまいます。"
            ),
        },
        {
            "start_line": 12,
            "end_line": 14,
            "title": "_pad — base64url パディングの補完",
            "explanation": (
                "base64url ではパディングの = が省略されることがあるため、長さを 4 の倍数に整える補助関数です。"
                "decode_token がペイロードを正しくデコードできるようにするための下ごしらえです。"
            ),
        },
        {
            "start_line": 17,
            "end_line": 19,
            "title": "encode — 署名付きトークンの発行",
            "explanation": (
                "クレームを base64url 化し、署名を付けてトークンを発行します。ここで付けた署名を、本来は "
                "decode_token 側で検証して改ざんを検出すべき、という対になる処理です。"
            ),
        },
    ],
    "src/catalog/search.ts": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "検索フィルタ生成の入口",
            "explanation": (
                "buildFilters は検索クエリ q を受け取り、検索エンジンに渡す Filter の配列を組み立てて返します。"
                "ユーザーが指定した絞り込み条件を、API が扱える形式に変換する役割です。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 6,
            "title": "条件ごとのフィルタ追加",
            "explanation": (
                "3〜6 行目で、カテゴリ・最低価格・最高価格・ブランドの各条件について『指定があれば対応するフィルタを"
                "配列に追加する』処理を並べています。ユーザーが指定した条件だけが検索に反映される仕組みです。"
            ),
        },
        {
            "start_line": 7,
            "end_line": 8,
            "title": "組み立て結果の返却",
            "explanation": (
                "組み上がったフィルタ配列を返します。呼び出し側はこれを検索クエリに渡し、条件に合う商品を絞り込みます。"
            ),
        },
    ],
    "src/inventory/stock.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "現在庫の参照",
            "explanation": (
                "reserve は SKU（商品識別子）と数量を受け取って在庫を引き当てる処理です。まず 2 行目で在庫テーブル "
                "STOCK から現在の在庫数を取得します（未登録の商品は 0 として扱います）。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 4,
            "title": "在庫の確認",
            "explanation": (
                "3〜4 行目で、要求された数量が現在庫を上回っていないかを確認します。足りない場合は OutOfStock を"
                "送出して、在庫切れであることを呼び出し側に知らせます。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 6,
            "title": "引当の確定",
            "explanation": (
                "在庫が足りていれば、5 行目で在庫数を要求ぶんだけ減らし、6 行目で確保済みを表す Reservation を"
                "返します。これで購入分の在庫が押さえられます。"
            ),
        },
    ],
    "src/user/profile.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "更新対象の取得",
            "explanation": (
                "update_profile はユーザー ID と更新内容 patch を受け取り、2 行目で対象のユーザーを読み込みます。"
                "プロフィール編集画面からの変更を反映するための処理です。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 4,
            "title": "変更内容の反映",
            "explanation": (
                "3〜4 行目で、patch に含まれる各項目を対応するユーザー属性へ順番に設定していきます。送られてきた"
                "変更内容を、ユーザーオブジェクトへ書き写す処理です。"
            ),
        },
        {
            "start_line": 5,
            "end_line": 5,
            "title": "保存",
            "explanation": ("すべての変更を反映したユーザーを 5 行目で保存し、更新内容を永続化します。"),
        },
    ],
    "src/shipping/shipping.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "配送業者の選定",
            "explanation": (
                "create_shipment は注文をもとに出荷を作成する処理です。2 行目で、注文の配送先地域に応じて適切な"
                "配送業者（キャリア）を選びます。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 3,
            "title": "配送ラベルの発行",
            "explanation": (
                "3 行目で、選んだキャリアの API を呼び出して配送ラベルを発行します。ここで外部の配送業者システムと"
                "連携します。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 5,
            "title": "追跡番号の記録",
            "explanation": (
                "発行されたラベルから追跡番号を取り出して注文に記録し（4 行目）、ラベルを返します（5 行目）。"
                "以降、ユーザーはこの追跡番号で配送状況を確認できます。"
            ),
        },
    ],
    "src/notifications/email.py": [
        {
            "start_line": 1,
            "end_line": 2,
            "title": "テンプレートの取得",
            "explanation": (
                "send_order_email は注文確認メールを送る処理です。2 行目で『注文確認(order_confirm)』用のメール"
                "テンプレートを取り出します。"
            ),
        },
        {
            "start_line": 3,
            "end_line": 3,
            "title": "本文の生成",
            "explanation": (
                "3 行目で、注文オブジェクトの各項目をテンプレートに差し込み、メール本文を組み立てます。テンプレート"
                "中のプレースホルダを、実際の注文内容で置き換える処理です。"
            ),
        },
        {
            "start_line": 4,
            "end_line": 4,
            "title": "送信",
            "explanation": ("4 行目で、組み立てた本文をユーザーのメールアドレス宛に SMTP で送信します。"),
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
            "title": "前半: 入力と処理の準備",
            "explanation": "何を受け取り、どんな前提のもとで処理を始めるか（入力・初期化・前提条件）を読み解きます。",
        },
        {
            "start_line": mid + 1,
            "end_line": total,
            "title": "後半: 中核処理と結果",
            "explanation": (
                "中核となる処理（計算・DB への読み書き・状態の更新）と、何を結果として返すかの流れを追います。"
            ),
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
                        # 先頭 2 ステップは学習済みにして進捗を「一部完了」にする（進捗バー/オンボーディング用）。
                        completed=order < 2,
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


logger = logging.getLogger(__name__)

# Bump this whenever the demo dataset's CONTENT changes (learning plans / quizzes / walkthroughs /
# graph / code debts …). The startup guard reseeds the demo only when the applied version differs,
# so edits show up on the next deploy without wiping an in-progress demo on every boot.
DEMO_SEED_VERSION = "7"  # v7: 学習プラン先頭 2 ステップを完了済みに（進捗デモ/オンボーディング用）

_SEED_VERSION_KEY = "demo_seed_version"  # app_metadata row key
_SEED_LOCK_KEY = 690690690  # fixed pg advisory-lock key for this script (serialize replicas)


async def refresh_demo_if_stale() -> bool:
    """Reseed the demo dataset on startup iff its content version changed (``DEMO_MODE_ENABLED`` only).

    ``seed()`` is idempotent (skips existing rows), so content edits require a reset+reseed to take
    effect. This gates on ``DEMO_SEED_VERSION`` stored in ``app_metadata`` and serializes replicas with
    a Postgres advisory lock, so exactly one instance reseeds and only when the version actually
    changed (a shared DB means the others just read the refreshed rows). Best-effort: callers should
    guard so a failure never blocks app startup.

    Returns:
        ``True`` if a reseed ran, ``False`` otherwise (disabled / already current / lock not acquired).
    """
    if not settings.DEMO_MODE_ENABLED:
        return False
    # The advisory lock is CONNECTION-scoped, so hold it on a dedicated session that never commits
    # (committing would rotate the pooled connection and the unlock would land on a different one).
    # All real work — version read, reset, reseed, marker upsert — runs on SEPARATE sessions.
    async with app_db.sa_async_session_maker() as lock_session:
        acquired = (await lock_session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SEED_LOCK_KEY})).scalar()
        if not acquired:
            return False  # another replica is (re)seeding; the shared DB will reflect its result
        try:
            async with app_db.async_session_maker() as check_session:
                marker = await check_session.get(AppMetadata, _SEED_VERSION_KEY)
                current = marker.value if marker is not None else None
            if current == DEMO_SEED_VERSION:
                return False

            async with app_db.sa_async_session_maker() as reset_session:
                await reset_analysis(reset_session)  # clear the demo org's seeded analysis rows (demo-only)
            async with app_db.async_session_maker() as seed_session:
                await seed(seed_session)

            async with app_db.async_session_maker() as mark_session:
                marker = await mark_session.get(AppMetadata, _SEED_VERSION_KEY)
                if marker is None:
                    mark_session.add(AppMetadata(key=_SEED_VERSION_KEY, value=DEMO_SEED_VERSION))
                else:
                    marker.value = DEMO_SEED_VERSION
                    mark_session.add(marker)
                await mark_session.commit()
            logger.info("demo dataset reseeded (version=%s)", DEMO_SEED_VERSION)
            return True
        finally:
            # Release on the same still-open, never-committed lock connection.
            await lock_session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SEED_LOCK_KEY})


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
