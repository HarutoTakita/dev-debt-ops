# ゲストデモ（GitHub アカウント不要の「お試しはこちら」）でサンプルプロジェクトを体験できるようにする

## 概要

現在ログインは **GitHub SSO（OAuth）必須**で、GitHub アカウントを持たない人はアプリの体験ができない。
ハッカソン審査用の公開に向けて、**ログイン画面に「お試しはこちら」ボタン**を追加し、GitHub 認証なしで
**事前にシードしたサンプルプロジェクト**に入って、理解負債（Knowledge Debt）中心のプロダクト体験
（Overview → コード品質マップ → Knowledge Galaxy → 学習ユニット/クイズ → 学習プラン）を**読み取り中心 + クイズ実演**で
触れるようにする。

- **GitHub を必要とする操作（プロジェクト作成・リポジトリ接続・解析の再実行・返済 PR 生成）は guest では無効化**し、
  「GitHub でサインインすると使える」導線に置き換える。
- guest は**共有のシード済みデモ org / project を閲覧**し、**クイズは実際に解いて採点**まで体験できる
  （クイズ採点は Gemini/Vertex AI＝サービス側 ADC で動き、ユーザーの GitHub トークンを必要としない）。
- 本番では**設定フラグで無効化可能**（審査公開・stg では有効）。

## 背景・目的

### 現状（GitHub SSO 必須）

- ログイン画面 `frontend/src/routes/login/+page.svelte` は「GitHub でサインイン」ボタン 1 つのみ。
  `/api/v1/auth/github/authorize` → GitHub 同意 → `/login/callback` → `/api/v1/auth/github/callback` の OAuth 一本道。
- ルートガード `frontend/src/routes/[org]/+layout.ts` は `auth.isAuthenticated` でなければ `/login` へリダイレクト。
  認証状態は `auth.init()` が `GET /api/v1/users/me` で判定（`frontend/src/lib/stores/auth.svelte.ts`）。
- バックエンドはメール/パスワード登録ルータも積んでいる（`fastapi_users.get_register_router()`）が、実運用は GitHub OAuth のみ。
  ユーザー作成時 `UserManager.on_after_register()`（`backend/api/app/core/security.py`）が**個人 org を自動作成**する。
- プロジェクト作成 `POST /api/v1/orgs/{slug}/projects`（`api/v1/projects.py`）は `GitHubClientDep` を要求し、
  OAuth アカウントの GitHub トークン検証 → installation token mint を行う。**GitHub トークンが無いと作れない**。
- 解析パイプライン（`detect-debts` / `detect-knowledge-debts` / `cluster-features` / `analyze-galaxy` / `analyze-stack` /
  `quizzes/generate` 等）はいずれも GitHub トークン（リポジトリ読取）を要する。一方、**解析結果テーブルは GitHub なしで
  直接シード可能**（`project_id` は index のみで FK なし＝api 所有の projects に依存せず insert できる）。

### 目的

1. GitHub アカウントを持たない審査員/来訪者が、**1 クリックで**製品価値（理解負債の検知 → 学習返済ループ）を体験できる。
2. シードしたサンプルデータで、**主要画面が最初から「データあり」**の状態（空っぽのオンボーディングにしない）。
3. guest は GitHub 連携を持たないため、**GitHub/書込系の操作は安全に無効化**し、誤操作・不正利用を防ぐ。
4. 本番運用では**フラグで無効化**でき、審査公開時のみ有効にできる。

### 前提（依存）

- 認証基盤（fastapi-users + access/refresh cookie、`token_epoch`、`current_active_user`）＝実装済み。
- org / project モデルと org スコープ依存（`OrgScope` / `OrgAdminScope`、`api/deps.py`）＝実装済み。
- 解析結果モデルと**読み取り API**（overview / debts / galaxy / knowledge-units / quizzes(閲覧) / learning / tech-stack /
  jobs 状態）＝016/018/028/029/030/034/035/052/054/063 等で実装済み。本 issue はこれらの**読み取り経路にシードデータを流し込む**だけで、
  新しい解析ロジックは作らない。

## 設計

> 方針: **共有のデモ user + 共有のシード済みデモ org/project**。guest は GitHub/書込を無効化した**閲覧中心**だが、
> **クイズは実際に解いて採点**まで動く（採点は GitHub 非依存）。最小実装で審査に間に合わせることを優先する。
> （代替案「クリックごとに使い捨ての匿名 user を発行し履歴を分離」は `対象外・保留` 参照。）

### A. ゲストログイン（backend）

- **設定**: `DEMO_MODE_ENABLED: bool`（`backend/api/app/core/config.py`、既定 `false`。stg/審査公開で `true`）。
  `false` の時はデモ用エンドポイントを 404/無効にし、フロントのボタンも出さない（`GET /api/v1/config` 等で公開）。
- **User フラグ**: `User.is_demo: bool = False`（`backend/api/app/models/user.py` + Alembic マイグレーション追加。**api が所有**）。
  guest ユーザーを識別し、ガードとバナー出し分けに使う。`is_superuser` は必ず `False`。
- **エンドポイント**: `POST /api/v1/auth/demo`（`api/v1/auth_demo.py` 新規、`auth.py` から `DEMO_MODE_ENABLED` 時のみ include）。
  - OAuth/パスワード不要。**共有デモ user**（`email = "demo@devdebtops.example"`, `display_name = "ゲスト"`, `is_demo=True`）を
    取得（無ければ作成）し、`auth_custom.py` の `login()` と**同じ**アクセス + リフレッシュ cookie を発行する
    （`EpochCheckedJWTStrategy` の access + DB-backed refresh）。`on_after_login` 相当で `last_active_at` 更新。
  - デモ user は `on_after_register` の個人 org 自動作成を**通さない**（直接作成 or シードで org を用意するため）。
  - 冪等: 毎回同じデモ user に対して新しいトークンを発行するだけ。`204`（cookie set）を返す。
  - レート制限は**エッジ（Cloud Armor、issue 017 系）**で `/api/v1/auth/demo` に付与（CLAUDE.md のレート制限方針）。
- `GET /api/v1/users/me` のレスポンス（`UserRead`）に `is_demo` を含める（フロントの出し分け用）。

### B. シードデータ（backend、冪等スクリプト）

- `backend/api/app/scripts/seed_demo.py`（新規）。`python -m app.scripts.seed_demo` で実行、**冪等**（安定 slug/id で upsert）。
  デモ org/project が無ければ作成し、解析結果テーブルにサンプル行を投入する。
- 作成物（安定 slug）:
  - **Org**: `slug="demo"`, `name="お試しデモ"`, `is_personal=False`, `created_by=デモ user`。デモ user を `OrgMember`（role=member）に追加。
  - **Project**: `slug="sample-shop"`（org `demo` 配下）, `repo_full_name="devdebtops/sample-shop"` 等の**ダミー GitHub メタ**
    （`github_repo_id=None`。guest は GitHub を叩かないので実在不要）。
  - **解析結果**（`shared/shared/models/` のテーブルへ直接 insert。理解負債中心のストーリーが映えるよう人手でキュレートした少量データ）:
    `AnalysisRun`（最新 + 過去数回）/ `RepoFile` / `Feature` + `FeatureFile`（機能クラスタ 2-3）/ `Dependency` /
    `FileKc`（Knowledge Coverage、低 KC のホットスポットを数件）/ `KnowledgeDebt`（AI 生成痕跡・著者離脱・未レビュー 等 2-3）/
    `CodeDebt`（重複/複雑度/dead 等 3-5、二軸マトリクスに乗る分布）/ `TechStack` / `DebtTrendPoint`（4 週分の推移）/
    `QuizSession`（低 KC ファイル由来の L1–L5 設問。**未回答状態**で投入）/ `LearningPlan`(+`LearningStep`/`LearningResource`)。
  - `AssignedDeveloper` 等、画面に出るなら少量添える。
- 安全策: シード行は**デモ org 配下にのみ**作る。`reset`（既存デモデータ削除 → 再投入）サブコマンドも用意（審査前リセット用）。
- 実行タイミング: ローカルは手動 `python -m app.scripts.seed_demo`。stg デプロイ時に**一度** seed を流す（Cloud Run ジョブ or
  デプロイ後フック。Alembic データマイグレーションには載せない＝環境限定にするため）。`DEMO_MODE_ENABLED` 時のみ。

### C. デモ用ガード（backend、GitHub/書込を無効化）

- `api/deps.py` に `BlockDemoWrite`（仮）依存を追加: `current_user.is_demo` が True の操作のうち、
  **GitHub トークンを要する/破壊的なもの**は `403`（`detail={"reason": "demo_readonly"}`）で弾く。対象:
  - プロジェクト作成 `POST /orgs/{slug}/projects`、リポジトリ一覧 `GET /github/repositories`、
    解析トリガ各種（`detect-debts` / `detect-knowledge-debts` / `cluster-features` / `analyze-galaxy` / `analyze-stack` /
    `quizzes/generate` / `baseline-*`）、返済 PR 生成、メンバー招待/ロール変更/削除、org/project 設定変更。
- **許可**（guest が触れる）: 上記 B の読み取り API 全般（overview / debts / galaxy / knowledge-units / learning / tech-stack /
  jobs 状態 / project 一覧・詳細 / orgs / users/me / members 閲覧）と、**クイズの受験/採点**
  （`quizzes/{id}/submit` 等＝`quiz_grading` は GitHub 非依存。ただしクイズ**生成**は不可）。
  - クイズ採点が非同期ジョブ（`quiz_grading`）の場合、ローカルは in-process mock-worker（issue 016）、stg は Cloud Tasks→service で動く。
- 実装は「GitHub トークン解決（`resolve_installation_id` / `GitHubClientDep`）の手前で `is_demo` を弾く」のが簡潔。
  既存の `GitHubClientDep` 利用箇所に `BlockDemoWrite` を併用するか、`resolve_installation_id` 内で `is_demo` を 403 にする。

### D. フロントエンド

- **ログイン画面** `routes/login/+page.svelte`: GitHub ボタンの下に**第2ボタン「お試しはこちら（GitHub 不要）」**。
  押下で `POST /api/v1/auth/demo`（`credentials: "include"`）→ `auth.init()` → **デモ org/project のダッシュボードへ**
  （`/demo/sample-shop` 等へ `goto`）。`DEMO_MODE_ENABLED`（`/api/v1/config`）が false の時はボタンを出さない。
- **auth ストア** `stores/auth.svelte.ts`: `user.is_demo` を保持し `get isDemo()` を公開。
- **デモバナー**（`components/shell/` に常設、`isDemo` 時のみ）: 「これはサンプルデータのデモ環境です。
  自分のリポジトリを解析するには GitHub でサインイン」＋ サインイン CTA（`/login`）。
- **GitHub/書込 UI の無効化**: `isDemo` の時、プロジェクト作成・「解析」CTA（`analysis-run-cockpit`）・リポジトリ接続・
  返済 PR・設定変更ボタンを**非活性 + Tooltip**（「デモでは利用できません。GitHub でサインインしてください」）。
  ルート的に到達した場合も 403 をハンドリングして同メッセージを表示。**クイズ/学習の閲覧・受験は活性**のまま。
- **ルートガード**: guest も認証済みなので既存 `[org]/+layout.ts` を通過する（変更最小）。
- 既存 OAuth 導線・コールバックは**不変**。

### E. i18n（Paraglide ja/en）

- 追加文言: 「お試しはこちら（GitHub 不要）」/ デモバナー本文 + CTA / 無効化 Tooltip /「デモでは利用できません」エラー。
  ja を主・en を従（CLAUDE.md）。

### セキュリティ

- `DEMO_MODE_ENABLED=false`（既定）の本番ではデモ login が無効。stg/審査のみ有効化。
- デモ user は `is_superuser=False`、GitHub OAuth アカウントを持たない（=GitHub API を一切叩けない）。
- C のガードで GitHub/書込/破壊的操作を 403。共有デモ user の読み取りは安全（シードデータのみ）。
- `/api/v1/auth/demo` はエッジ（Cloud Armor）でレート制限。リフレッシュ・`token_epoch` 等の既存ローテーション機構をそのまま使う。

## タスク

### backend（auth / config / guard）
- [ ] `core/config.py` に `DEMO_MODE_ENABLED`（既定 false）。`GET /api/v1/config` 等で公開しフロントが参照。
- [ ] `models/user.py` に `is_demo: bool = False` 追加 + Alembic マイグレーション（api 所有）。
- [ ] `api/v1/auth_demo.py` 新規: `POST /api/v1/auth/demo`（共有デモ user 取得/作成 → access+refresh cookie 発行、204）。
      `auth.py` で `DEMO_MODE_ENABLED` 時のみ include。
- [ ] `UserRead` に `is_demo` を露出（`/users/me`）。
- [ ] `api/deps.py` に `BlockDemoWrite` 依存（or `resolve_installation_id` 内ガード）で GitHub/書込系を `is_demo` 時 403。
      対象エンドポイントへ適用。

### backend（seed）
- [ ] `app/scripts/seed_demo.py` 新規（冪等）: デモ org（slug `demo`）+ project（slug `sample-shop`）+ デモ user の OrgMember +
      解析結果テーブル一式のサンプル投入。`reset` サブコマンド付き。
- [ ] stg デプロイで seed を一度流す手順（Cloud Run ジョブ or デプロイ後フック、`DEMO_MODE_ENABLED` 時のみ）を整備（infra/CI は最小で可、follow-up 明記でも可）。

### frontend
- [ ] `routes/login/+page.svelte`: 「お試しはこちら」ボタン（`DEMO_MODE_ENABLED` 時のみ）→ `POST /auth/demo` → `auth.init()` → デモ org へ。
- [ ] `stores/auth.svelte.ts`: `isDemo` 公開。`lib/api/client.ts` に `demoLogin()`。
- [ ] デモバナー（`isDemo` 常設）+ GitHub/書込 UI の非活性 + Tooltip + 403 ハンドリング。
- [ ] i18n（ja/en）追加。

### test
- [ ] backend: `POST /auth/demo` が cookie を発行し `/users/me` が `is_demo=true` を返す（`DEMO_MODE_ENABLED` on/off の両方）。
- [ ] backend: `is_demo` user が GitHub/書込エンドポイントで 403、読み取り + クイズ受験で 200。
- [ ] backend: `seed_demo` 冪等（2 回実行で重複しない）+ デモ project の overview/galaxy/quizzes 読み取りが非空。
- [ ] frontend（vitest）: ログインボタン表示（フラグ依存）、`isDemo` 時の UI 無効化、デモログイン → 認証状態遷移。

## 完了条件

- `DEMO_MODE_ENABLED=true` の環境で、ログイン画面に「お試しはこちら」が表示され、押下で**GitHub 認証なし**にログインし、
  シード済みデモプロジェクトのダッシュボードに到達できる。
- デモプロジェクトの主要画面（Overview / コード品質マップ / Knowledge Galaxy / 学習ユニット / 学習プラン / クイズ一覧）が
  **最初からデータあり**で表示される。
- guest は**クイズを実際に解いて採点結果**まで体験できる（GitHub 非依存）。
- guest が GitHub/書込操作（プロジェクト作成・解析実行・返済 PR・設定変更等）を行うと UI で無効化され、API も 403 を返す。
- 「デモ環境」バナーと「GitHub でサインイン」導線が表示される。
- `DEMO_MODE_ENABLED=false`（既定）ではデモ login が無効で、ボタンも出ない。
- backend: `uv run --directory api pytest` / ruff / ty が通る。frontend: `bun run check` / `lint` / `test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Added`（ゲストデモ / お試し動線）を追記。

## 対象外・保留

- **クリックごとの使い捨て匿名 user（履歴分離）**: 本 issue は共有デモ user。同時アクセス時にクイズ履歴等が混ざるのは
  審査用途として許容する。完全分離（per-guest user + 期限付きクリーンアップ job）は後続。
- guest によるリポジトリ接続・実解析・返済 PR（GitHub 必須）の体験。
- デモデータの自動更新/自動再解析。シードは手動/デプロイ時の一括投入のみ。
- 役割別（PM/開発者）のデモ出し分け。

## 参考

### このリポジトリ（変更・参照対象）
- 認証: `backend/api/app/api/v1/auth.py` / `auth_custom.py`（`login`/`refresh`/`logout`）/ `core/security.py`（`UserManager`/`current_active_user`）/ `core/access_token.py`（`EpochCheckedJWTStrategy`）/ `models/user.py` / `models/oauth_account.py`。
- org/project: `models/org.py`（`Org`/`OrgMember`）/ `models/project.py` / `api/v1/projects.py`（作成は `GitHubClientDep` 必須）/ `api/deps.py`（`CurrentUser`/`OrgScope`/`OrgAdminScope`）/ `api/v1/github.py`（`resolve_installation_id`/`GitHubClientDep`）。
- 解析結果モデル: `backend/shared/shared/models/`（`analysis_run` / `code_debt` / `knowledge_debt` / `file_kc` / `feature`(+`feature_file`) / `dependency` / `repo_file` / `tech_stack` / `debt_trend_point` / `quiz_session`(+`quiz_result`/`quiz_answer`) / `learning_plan`）。
- 読み取り API: overview / debts / galaxy / knowledge-units / learning / quizzes(閲覧) / jobs 状態（`api/v1/` 各ルータ）。
- フロント: `routes/login/+page.svelte` / `routes/login/callback/+page.svelte` / `stores/auth.svelte.ts` / `routes/[org]/+layout.ts`（ガード）/ `lib/api/client.ts`（`apiFetch`）/ `components/shell/`（バナー設置）/ `components/overview/analysis-run-cockpit.svelte`（解析 CTA の無効化）。
- 非同期基盤（クイズ採点等）: issue 016（Cloud Tasks + in-process mock-worker）/ 034（quiz_generation/grading）。
- レート制限/インフラ: issue 017（Cloud Armor エッジ）。

### 関連 Issue
- 066 オンボーディングガイド（初回ツアー）— デモ初回体験とも親和。
- 058/059 リポジション（理解負債中心）— デモはこのナラティブを最短で見せる導線。

### 規約（CLAUDE.md）
- 認証は access(JWT 5分)+refresh(DB 7日) cookie 分離・`token_epoch`。レート制限は**エッジ（Cloud Armor）**で強制。
- シークレットは Secret Manager（平文環境変数禁止）。DB 所有権は api（Alembic/エンジン）。
- フロントは Svelte 5 runes・shadcn `ui/` 読取専用・i18n ja/en・kebab-case。CHANGELOG 日本語。
- PATCH は部分更新。`from shared.models import ...` で共有 ORM を利用。
