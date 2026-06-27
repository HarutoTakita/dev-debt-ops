# 学習プラン生成パイプラインと取得/進捗 API を実装する（チーム資産浮上）

## 概要

学習プラン画面（issue 012）は現在、フロントの `frontend/src/lib/mocks/learning-plan.ts:5`
（`mockLearningPlan`）をルートローダ `frontend/src/routes/[org]/[project]/learning/+page.ts:10`
が**直接 return** している。バックエンドは一切無く（`client.ts` に learning 系関数は存在しない）、
`learningPlanSchema`（`frontend/src/lib/api/schemas.ts:482`）の契約だけが固まっている状態である。

本 issue はこの裏側を実装する。ナレッジ返済ループ「検知 → クイズ → ギャップ抽出 →
**学習プラン** → 再クイズ」（issue 012 概要、§5.3 → §5.4）の遷移先を実データ化する。
最大の特徴は **チーム内資産（死蔵 ADR / PR レビューコメント / コード / 社内動画）を
外部資源候補（公式 docs / 技術書）より「上段」に浮上させる** こと（issue 012 §5.4 並び順、
`docs/issue/012-learning-plan-team-assets.md:302-315`）。

設計方針（CLAUDE.md / 018 パターン）に従い、重い生成処理（ADR 走査・PR コメント抽出・
死蔵度算出・Gemini による外部候補生成）は **service の非同期パイプライン**に載せ、api は
**enqueue + 取得/進捗配信 + ポーリング**に徹する。

- POST `.../learning/plans?attempt_id=...` → `202 {job_id}`（issue 034 の `quiz_result.gap_concepts` を入力に生成 enqueue）
- GET `.../learning/plans/{plan_id}` → `learningPlanSchema` 形を配信
- PATCH `.../learning/plans/{plan_id}/steps/{order}` → ステップの `completed` を部分更新（PATCH 規約）

レスポンスは **snake_case 維持**（schemas.ts がそのまま parse できるよう、`stack.py` の
`TechStackOut` 同様に素の `BaseModel` で配信する。`Job.result_data` の camelCase 規約とは別系統）。

## 背景・目的

### 現状（フロントのみ・モック直読み）

- 描画: `frontend/src/routes/[org]/[project]/learning/+page.ts:8-14` が `mockLearningPlan` を
  return（`ssr = false`、`?from=quiz` を受けるのみ）。`client.ts` に `getLearningPlan` /
  `patchStep` / `generatePlan` は無い（grep `learning|Learning|Plan` で 0 件）。
- 契約: `schemas.ts:459-494` に `resourceOriginSchema`（`team` / `external`）/
  `resourceKindSchema`（`adr` / `video` / `pr_comment` / `wiki` / `docs` / `book` / `article` / `code`）/
  `resourcePrioritySchema`（`required` / `recommended` / `supplementary` / `hands_on`）/
  `learningResourceSchema`（`id` / `origin` / `kind` / `title` / `source_ref` nullable /
  `url` nullable / `estimated_minutes` nullable / `priority` / `dormant_days` nullable optional）/
  `learningStepSchema`（`order` / `resource` / `completed`）/
  `learningPlanSchema`（`id` / `gap_concepts: string[]` / `steps[]` / `estimated_total_minutes`）。

### 目的

1. learning の永続化を **shared ORM**（`learning_plan` / `learning_step` / `learning_resource`）として新設し、
   テーブル作成は **api 所有の Alembic 0006** で行う（`tech_stack.py` / `0003` / `0005` 雛形）。
2. 重い生成を **service の `learning_plan_generation` パイプライン**（3 段: internal_asset_search →
   external_resource_search → plan_generator）に載せ、`JobType` に追加して registry に登録する（`stack_analysis.py` 雛形）。
3. api を「生成 enqueue（202）+ 取得配信 + ステップ進捗 PATCH」に薄くする。
4. フロント `client.ts` に `getLearningPlan` / `patchStep` / `generatePlan` を新設し、
   `learning/+page.ts` のモック直読みを実 API へ差し替える。

### 前提 Issue（depends_on）

- **Issue 034** `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — クイズ生成・採点。
  本 issue の生成入力 = 034 の `quiz_result.gap_concepts`（`schemas.ts:356` の `Concept[]` = `{id,label}`）と
  `quiz_session`（`developer_id` = `users.id`、`project_id`）。034 の採点完了が学習プラン生成のトリガ元
  （034 の `quiz_result.learning_plan_id` nullable と相互参照）。**本 issue は採点（gap 供給）を実装しない** — 034 が供給する。

> 034 が未完了の場合、`POST .../learning/plans` は `attempt_id`（= quiz session id）を解決できないため、
> 当面は `gap_concepts` を直接 body で受ける経路を暫定とし、034 完了後に `attempt_id` 解決へ正式接続する。

## データモデル

すべて **shared ORM**（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）。
`TechStack` 同様に id は `uuid.uuid4` default、時刻は `DateTime(timezone=True)`、JSON 列は
`sa_column=Column(JSON, ...)`。テーブル作成は **api が Alembic で所有**（連番 `0006`、雛形 `0003_add_tech_stacks.py` / `0005_add_jobs.py`）。
`backend/shared/shared/models/__init__.py:3-6` に **import 順 app→shared**（既存は api 由来モデル無し、shared の `Job` / `TechStack` に追記）で re-export する。

### 新規テーブル

| テーブル | 主なカラム | 備考 |
|---|---|---|
| `learning_plan` | `id` (uuid4 PK) / `project_id` (FK `projects.id`, index) / `gap_concepts` (JSON = `list[str]`) / `estimated_total_minutes` (int) / `quiz_session_id` (FK nullable; 034 の `quiz_session`) / `created_at` (`DateTime(timezone=True)`) | プランのヘッダ。`gap_concepts` は **正規化後の `string[]`**（下記） |
| `learning_step` | `id` (uuid4 PK) / `plan_id` (FK `learning_plan.id`, index) / `order` (int) / `completed` (bool default False) / `completed_at` (`DateTime(timezone=True)` nullable) / `resource_id` (FK `learning_resource.id`) | `(plan_id, order)` UniqueConstraint。PATCH の更新対象 |
| `learning_resource` | `id` (uuid4 PK) / `project_id` (FK `projects.id`, index) / `origin` (str: `team` / `external`) / `kind` (str: 8 種) / `title` / `source_ref` (nullable) / `url` (nullable) / `estimated_minutes` (int nullable) / `priority` (str: 4 種) / `dormant_days` (int nullable) / `origin_meta` (JSON: 出自メタ adr_path / pr_number / commit_sha 等) | resource を `learning_step` 埋め込みにせず FK 分離し再利用可に。enum 値は `schemas.ts:459-461` と一致 |

> **gap_concepts 型変換（正規形の確定）:** quiz の `quiz_result.gap_concepts` は `Concept[]`
> （`{id,label}`、`schemas.ts:356`）だが、`learningPlanSchema.gap_concepts` は `string[]`
> （`schemas.ts:484`、モック `["distributed_caching","ADR-0012","RedisClient"]`、`learning-plan.ts:7`）。
> **本 issue の正規形 = `Concept.id` を採用した `list[str]`** とする（プラン生成入力で `[c.id for c in concepts]`）。
> ラベルは生成された resource の `title` 側に反映する。`learning_plan.gap_concepts` には `string[]` を保存し、
> API もそのまま `string[]` で配信する（schemas.ts に一致）。

### pgvector / 死蔵検知の注記

- 埋め込み類似マッチング（gap_concept ↔ チーム資産）は pgvector で実現余地があるが、`CREATE EXTENSION vector` も
  vector 列も現状未配線（issue 026 で拡張有効化予定）。**本 issue は LIKE / ファイル走査ベース**で実装し、pgvector は対象外。
- `dormant_days` = 「最後に更新/閲覧されてからの経過日数」。GitHub の commit 日時・ファイル mtime から算出する
  （`internal_asset_search`、後述）。閲覧ログ・社内動画の取得元は外部 I/F 不明のため、ADR / PR / コード由来に限定する。

## API

すべて `projects.py` の `/orgs/{slug}/projects/{project_slug}/...` 配下に揃える
（`docs/issue/012-learning-plan-team-assets.md:271-279` の素の `/api/v1/learning/plans/{id}` は
プロジェクト単位方針と齟齬するため**プロジェクト配下へ寄せる**判断とする）。認可は `OrgScope`
（`backend/api/app/api/deps.py:64`）。Annotated DI param 順序は厳守（`stack.py:111-119` の並びを踏襲）。
`router.py`（`backend/api/app/api/v1/router.py`）に `learning_router` を include する。

| メソッド・パス | レスポンス / ステータス | 一致させる schema | 認可 |
|---|---|---|---|
| `GET .../learning/plans/{plan_id}` | `LearningPlanOut`（素の `BaseModel`, snake_case）/ 200, 404=未生成 | `learningPlanSchema`（`schemas.ts:482`） | `OrgScope` |
| `PATCH .../learning/plans/{plan_id}/steps/{order}` | `LearningStepOut` または更新後の `LearningPlanOut` / 200 | `learningStepSchema`（`schemas.ts:476`） | `OrgScope` |
| `POST .../learning/plans?attempt_id=...` | `JobEnqueuedOut`（`{job_id, status}`）/ 202 | `analyzeStackJobSchema` 相当（`job_id` / `status`） | `OrgScope` |

- `GET` レスポンスは `learningPlanSchema` を厳密に満たす（`steps[].resource` は `learning_resource` を join し
  `origin` / `kind` / `priority` / `source_ref` / `dormant_days` を snake_case で返す）。`response_model` で検証する。
- `PATCH .../steps/{order}` は body `{completed: bool}` を受け、該当 `(plan_id, order)` の `completed` /
  `completed_at` のみを**部分更新**（PATCH 規約。`projects.py:115-142` の PATCH パターンを踏襲）。
- `POST .../learning/plans` は `enqueue_job(... job_type=JobType.LEARNING_PLAN_GENERATION, payload=..., created_by=current_user.id)`
  を呼び `202 {job_id}` を返す（`stack.py:105-143` 雛形、`JobEnqueuedOut`=`backend/api/app/schemas/job.py:8`）。
  ポーリングは既存 `GET /api/v1/jobs/{job_id}`（`backend/api/app/api/v1/jobs.py`）をそのまま利用。
  生成完了後の `plan_id` は `Job.result_data` 経由で取得し、`GET .../learning/plans/{plan_id}` へ遷移する。

## パイプライン・非同期

### JobType / スキーマ / registry

- [ ] `backend/shared/shared/enums.py` の `JobType` に `LEARNING_PLAN_GENERATION = "learning_plan_generation"`
  を追加（lowercase snake_case = queue path、`_`→`-` で `learning-plan-generation`。`STACK_ANALYSIS` の隣）。
- [ ] `backend/shared/shared/schemas/learning_plan.py` を新設し `LearningPlanGenerationRequest`（`JobRequestBase`
  継承、`project_id` / `gap_concepts: list[str]`（正規化後）/ `quiz_session_id: str | None` / `repo_full_name` /
  `github: GitHubRef`（installation_id 方式 B、`stack_analysis.py:45` の `GitHubRef` を再利用 import））/
  `LearningPlanGenerationResult`（`JobResultBase` 継承、`plan_id: str` / 生成 step 件数等）を定義
  （`backend/shared/shared/schemas/job.py:12-27` の base を継承、`backend/shared/shared/schemas/stack_analysis.py` 雛形）。
- [ ] `backend/service/service/registry.py` の `PIPELINES` に
  `JobType.LEARNING_PLAN_GENERATION.value: (LearningPlanGenerationRequest, LearningPlanGenerationResult, learning_plan_generation.process)`
  を追加（`registry.py:15-18` の三つ組規約）。

### service パイプライン（`process` 3 段）

`backend/service/service/pipelines/learning_plan_generation.py` を新設。`process(request, ctx)` で
`ctx.session` に DML（`stack_analysis.py:process` 雛形、`shared.worker.run_task` が冪等・Job ライフサイクルを吸収）。

1. **internal_asset_search** — `GitHubGitClient`（`backend/service/service/services/github_git_client.py`）の
   `get_repository_tree` / `get_file_content` で `adr/`（Diátaxis: `docs/adr/`）走査・PR レビューコメント・コードを横断検索。
   commit 日時 / mtime から `dormant_days` を算出し、`origin="team"` の `learning_resource` を生成。
   GitHub トークンは **方式 B**（`installation_id` のみ搬送、service が `GitHubAppService` で Secret Manager から mint。
   `stack_analysis.py:28` / `github_app.py`）。
2. **external_resource_search** — `gemini_stack_service`（Vertex AI + ADC、`backend/service/service/services/gemini_stack_service.py`、
   `_vertex_model_name()` で `projects/` 始まりにし ADC 選択）で外部候補（公式 docs / 技術書 / 記事）を生成し、
   `origin="external"` の `learning_resource` を生成。**URL の検証**（到達性・スキーム）を行い不正 URL を弾く。
3. **plan_generator** — `team` を**必ず上段**・`external` を下段に分割（issue 012 §5.4、`012:302-315`）。
   `priority`（required → recommended → supplementary → hands_on）で `learning_step.order` を構築し、
   `estimated_minutes` 合計を `learning_plan.estimated_total_minutes` に積む。`learning_plan` / `learning_step` を upsert。

### 定期スキャン

死蔵資産インデックスの定期更新は Cloud Functions / Cloud Scheduler / Pub-Sub（CLAUDE.md、issue 037）。**本 issue では手動トリガ（クイズ採点完了 → 生成 enqueue）のみ**。

## タスク

### shared

- [ ] `backend/shared/shared/models/learning_plan.py` に `LearningPlan` / `LearningStep` / `LearningResource` を新設
  （`tech_stack.py:19-44` 雛形、uuid4 PK / `DateTime(timezone=True)` / JSON 列 / UniqueConstraint）。
- [ ] `backend/shared/shared/models/__init__.py:3-6` に 3 モデルを import & `__all__` 追記（import 順 app→shared）。
- [ ] `backend/shared/shared/enums.py` の `JobType` に `LEARNING_PLAN_GENERATION` 追加。
- [ ] `backend/shared/shared/schemas/learning_plan.py` に Request / Result スキーマ新設（`GitHubRef` は `stack_analysis.py:45` を import）。

### api

- [ ] `backend/api/app/alembic/versions/0006_add_learning_plans.py` を新設し 3 テーブル + index + FK + `(plan_id, order)`
  UniqueConstraint を作成（`down_revision="0005"`、`0005_add_jobs.py:13-40` 雛形、naming は `base.py` convention）。
- [ ] `backend/api/app/api/v1/learning.py` を新設（`APIRouter(tags=["Learning"])`、`stack.py` の構成に倣う）:
  GET `.../learning/plans/{plan_id}` / PATCH `.../learning/plans/{plan_id}/steps/{order}` / POST `.../learning/plans`。
  レスポンス Out モデルは素の `BaseModel`（snake_case、`stack.py:36-65` の `TechStackOut` パターン）。
- [ ] `backend/api/app/api/v1/router.py:9` 付近で `learning_router` を import し `:19` 付近で `include_router`。
- [ ] POST は `enqueue_job`（`backend/api/app/services/job_orchestrator.py`）を `stack.py:135-142` どおりに呼び `202` を返す。
  `attempt_id`（quiz session id）から 034 の `quiz_result.gap_concepts`（`Concept[]`）を読み `[c.id ...]` に正規化して payload へ。

### service

- [ ] `backend/service/service/pipelines/learning_plan_generation.py` に `process(request, ctx)` 3 段を実装
  （`stack_analysis.py` 雛形、`ctx.session` で upsert）。
- [ ] `backend/service/service/registry.py:15-18` の `PIPELINES` に三つ組登録。
- [ ] `internal_asset_search` で `GitHubGitClient`（`github_git_client.py`）+ `GitHubAppService`（`github_app.py`、方式 B）を利用。
- [ ] `external_resource_search` で `gemini_stack_service`（Vertex AI + ADC）を利用し URL 検証を行う。

### frontend

- [ ] `frontend/src/lib/api/client.ts` に `getLearningPlan(orgSlug, projectSlug, planId): Promise<LearningPlan>` /
  `patchStep(orgSlug, projectSlug, planId, order, completed): Promise<LearningStep>` /
  `generatePlan(orgSlug, projectSlug, attemptId): Promise<{job_id, status}>` を新設（`learningPlanSchema` 等で parse、snake_case 維持）。
- [ ] `frontend/src/routes/[org]/[project]/learning/+page.ts:8-14` の `mockLearningPlan` 直読みを `getLearningPlan` 実 API へ差し替え
  （`?from=quiz&attemptId=` の仮配線を `generatePlan` → ポーリング → `getLearningPlan` の正式導線へ）。
- [ ] ステップ完了トグルを `patchStep`（PATCH）に接続（resource-list / plan-progress コンポーネントは issue 012 既存を流用）。

### infra

- [ ] service runtime SA に Vertex AI（`roles/aiplatform.user`）と Secret Manager（GitHub App private key 参照）を付与
  （issue 017 / 037 の Terraform。本 issue では前提として記述のみ）。

### test

- [ ] api（`backend/api/tests/`）: GET が `learningPlanSchema` 形を返すこと（404=未生成）、PATCH `.../steps/{order}` が
  `completed` / `completed_at` のみ部分更新すること、POST が `202 {job_id}` を返し `Job(QUEUED)` 作成 + `MockTaskDispatcher.dispatch` が 1 回呼ばれること（他人プロジェクトを `OrgScope` で遮断）。
- [ ] service（`backend/service/tests/`）: `process` 3 段のパイプラインテスト（`GitHubGitClient` / Gemini をモック）。
  `team` が `external` より上段、`priority` 順に `order` が構築され `learning_plan` / `learning_step` が upsert されること。
  再配送（at-least-once）で二重生成されない冪等性（`shared.worker.run_task` 経由）。
- [ ] frontend（`frontend/src/lib/...`）: `client` の `getLearningPlan` / `patchStep` / `generatePlan` のユニットテスト（API モック）。

## 完了条件

- `learning/+page.ts` がモックではなく **実 API（`getLearningPlan`）** からプランを取得して描画する。
- POST `.../learning/plans` が `202 {job_id}` を返し、service が api リクエスト外で 3 段生成を実行、
  `learning_plan` / `learning_step` / `learning_resource` を Cloud SQL に永続化、`Job` を `COMPLETED` + `result_data`（`plan_id`）に直接書き込む。
- 生成プランで **team が必ず上段・external が下段**、`priority` 順に `order` が並ぶ（issue 012 §5.4）。
- PATCH `.../steps/{order}` でステップ `completed` が永続化され、再取得で反映される（部分更新）。
- レスポンスが `learningPlanSchema` を**そのまま parse 可能**（snake_case）。
- バックエンド: `cd backend && uv run --directory api pytest`（service も `--directory service`）/
  `uv run ruff check shared/shared api/app service/service && uv run ruff format --check ...` /
  `uv run ty check shared/shared api/app service/service` が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語、Keep a Changelog）に `Added`（学習プラン生成パイプライン + 取得/進捗 API）を追記。

## 対象外・保留

- クイズ採点・gap 抽出（**034 が供給**）。本 issue は `gap_concepts` を入力として受けるのみ。
- Galaxy 描画（gap_concepts=未踏星域 / steps[].completed=星点灯 の写像は issue 032 / 描画は別 issue）。
- pgvector 埋め込み類似マッチング（拡張有効化は issue 026、本実装は将来）。
- 死蔵資産インデックスの定期更新（Cloud Functions / Pub-Sub、issue 037）。
- 社内勉強会動画・閲覧ログの取り込み（取得元 I/F 不明、ADR / PR / コード由来に限定）。

## 参考

- 関連 Issue
  - `docs/issue/012-learning-plan-team-assets.md` — 学習プラン画面・Zod スキーマ・並び順ロジック（§5.4、`012:302-315`）
  - `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — **前提**。`quiz_result.gap_concepts`（`Concept[]`）供給元
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 非同期パイプライン（202 enqueue / registry 三つ組 / 方式 B）の雛形
  - `docs/issue/032-backend-galaxy-personal-kc-api.md` — gap_concepts / completed の Galaxy 写像（連携先）
  - `docs/issue/037-backend-periodic-scan-cloud-functions.md` — 定期スキャン（死蔵インデックス更新の将来基盤）
- フロント契約 / モック
  - `frontend/src/lib/api/schemas.ts:459-494` — `learningResourceSchema` / `learningStepSchema` / `learningPlanSchema`（snake_case）
  - `frontend/src/lib/mocks/learning-plan.ts:5` — `mockLearningPlan`（差し替え対象）
  - `frontend/src/routes/[org]/[project]/learning/+page.ts:8-14` — モック直読みローダ（差し替え対象）
  - `frontend/src/lib/api/client.ts` — learning 系関数を新設（現状 0 件）
- 既存バックエンド（流用・雛形）
  - `backend/api/app/api/v1/stack.py:105-167` — 202 enqueue / GET 配信 / 素の Out モデル（snake_case）
  - `backend/api/app/api/v1/projects.py:115-142` — `/orgs/{slug}/projects/{project_slug}` ルート・PATCH・`OrgScope`
  - `backend/api/app/services/job_orchestrator.py` — `enqueue_job` / `backend/api/app/schemas/job.py:8` — `JobEnqueuedOut`
  - `backend/api/app/api/v1/jobs.py` — `GET /jobs/{id}` ポーリング
  - `backend/service/service/pipelines/stack_analysis.py` — `process(request, ctx)` 雛形 / `_vertex_model_name()` ADC
  - `backend/service/service/registry.py:15-18` — 三つ組登録
  - `backend/service/service/services/github_git_client.py` / `github_app.py`（方式 B）/ `gemini_stack_service.py`（Vertex AI + ADC）
  - `backend/shared/shared/models/tech_stack.py` — ORM 雛形 / `backend/shared/shared/models/__init__.py` — re-export（app→shared）
  - `backend/shared/shared/schemas/stack_analysis.py:45` — `GitHubRef`（再利用）/ `backend/shared/shared/schemas/job.py:12-27` — base
  - `backend/shared/shared/enums.py` — `JobType`（追加先）
  - `backend/api/app/alembic/versions/0005_add_jobs.py` — マイグレーション雛形（次番 0006）
  - `backend/api/app/api/v1/router.py` — ルーター include 追加先
- 規約: CLAUDE.md / backend — Vertex AI + ADC（google-api-key 不使用）・Secret Manager 必須・WIF・方式 B・
  Annotated DI param 順序厳守・`models/__init__.py` import 順（app→shared）・JobType 追加・router 登録・PATCH 部分更新・
  ゲート（ruff / ty / pytest, bun check / lint / test:unit）・CHANGELOG（日本語）
