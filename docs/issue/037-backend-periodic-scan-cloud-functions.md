# 定期スキャン基盤を Terraform で追加する（Cloud Functions + Scheduler/Pub-Sub で巡回 enqueue）

## 概要

解析パイプライン（コード負債 028 / KC 029 / 知識負債 030）は、いずれも api の
**手動トリガ enqueue ルート**（`POST .../detect-debts` / `.../analyze-kc` /
`.../detect-knowledge-debts` → `202 {job_id}`）からしか起動できない。
CLAUDE.md が掲げる「**非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub トリガー）**」は
未実装で、Issue 017（GCP Terraform）は **定期スキャン用の Cloud Functions / Cloud Scheduler /
Pub/Sub を意図的にスコープ外**としている（`infra/gcp/apis.tf:4-6`・`infra/gcp/iam.tf:5-6`・
`infra/gcp/variables.tf:215-217`・`infra/bootstrap/gcp/roles.tf:5-7` に「将来の専用 issue で追加」と明記）。

本 issue は、その **将来の専用 issue** として、`infra/gcp/` と `infra/bootstrap/gcp/` に
**Cloud Scheduler → Pub/Sub → Cloud Functions** の定期スキャン経路を新設し、各 project を巡回して
analyze 系 Job（`code_debt_detection` / `kc_analysis` / `knowledge_debt_detection`）を
**既存の Cloud Tasks 基盤経由で enqueue** する。併せて、蓄積した `analysis_run`
（Issue 026 の共有テーブル）時系列から **`debt_trend_point`（週次スナップショット）を生成**し、
Issue 031 で読み取りのみ実装された Overview の `trend` を **実時系列化**する。

重い解析ロジック本体（028-030 の `process`）と配信 API（031）は **本 issue では作らない**。
本 issue は「**いつ・何を・冪等に enqueue するか**」と「**run 時系列から週次スナップショットを書く**」
という巡回オーケストレーションの裏側だけを所有する。

> WIF（long-lived 鍵不使用）・Secret Manager・GitHub App **方式 B**（`installation_id` のみ搬送、
> service が Secret Manager から token mint）は本 issue でも踏襲する。Pub/Sub 経由でも秘密はメッセージに
> 載せず、enqueue されるのは 028-030 と同じ `JobRequestBase` 派生ペイロード（`GitHubRef.installation_id`）である。

## 背景・目的

### 現状（手動 enqueue のみ・定期スキャンは未配線）

- analyze 系 Job は api のルートからの手動トリガでのみ起動する（028: `JobType.CODE_DEBT_DETECTION` /
  029: `JobType.KC_ANALYSIS` / 030: `JobType.KNOWLEDGE_DEBT_DETECTION`、いずれも
  `enqueue_job(session, dispatcher, blob_client, job_type=..., payload=..., created_by=current_user.id)`
  → Cloud Tasks → service `/tasks/{pipeline}`）。
- `analysis_run`（Issue 026、`shared/shared/models/analysis_run.py`：`project_id` / `commit_sha` / `branch` /
  `kind` / `job_id` / `status` / `created_at`）に解析スナップショットは蓄積されるが、その時系列から
  **週次の `debt_trend_point` を生成する書き手が居ない**。
- `debt_trend_point`（Issue 031 で新設、`debtTrendPointSchema` 形 = `week` / `code_debt_score` /
  `knowledge_coverage`、`(project_id, week)` ユニーク）は **読み取り配信（`GET .../overview` の `trend`）だけが
  実装済み**で、書き込みは「Issue 037 が `analysis_run` 時系列から生成」と明記されている
  （`docs/issue/031-backend-overview-and-debt-registry-api.md:118-120,303`）。よって現状の `trend` は常に
  空配列（フロントは空グラフで成立）。
- インフラ側は 017 が **Pub/Sub / Cloud Functions / Cloud Scheduler を一切作っていない**：
  - `infra/gcp/apis.tf:4-6` — `pubsub` / `cloudfunctions` / `cloudscheduler` / `eventarc` は有効化しない旨を明記。
  - `infra/gcp/iam.tf:5-6` — Pub/Sub SA / functions SA を作らない旨を明記。
  - `infra/gcp/variables.tf:215-217` — `container_image_functions` 変数を作らない旨を明記。
  - `infra/bootstrap/gcp/roles.tf:5-7` — deploy SA に `roles/pubsub.admin` / `roles/cloudfunctions.admin` /
    `roles/cloudscheduler.admin` を付与しない旨を明記（「A future scheduled-scan issue adds them there.」）。

### 目的

1. `infra/gcp/` に **Cloud Scheduler → Pub/Sub topic → Cloud Functions（2nd gen, Eventarc）** の定期スキャン経路を
   新設する。Cloud Function は **各 project を巡回**し、028-030 の analyze 系 Job を
   **既存の Cloud Tasks 基盤（`enqueue_job`）経由で enqueue** する（自前のキューは作らず 016/017 の経路に乗る）。
2. **冪等性・頻度・コスト制御**を設計する：同 `commit_sha` の `analysis_run` が既にあれば再 enqueue を抑止
   （`analysis_run.commit_sha` を冪等キーに活用。Issue 026 が「037 が同 commit の重複 run 抑止に使う」と明記
   `docs/issue/026-...:100,208`）。スキャン頻度・対象 project 数・1 回あたりの enqueue 上限を変数で制御する。
3. `analysis_run` 時系列から **週次の `debt_trend_point` を生成**し、Overview の `trend`（031）を実時系列化する。
4. **WIF / Secret Manager / 方式 B** を踏襲し、平文の秘密をメッセージ・環境変数に載せない。
5. 017 が将来送りにした **API 有効化・deploy SA ロール・variables** をこの issue 側で追記する
   （017 のコメントが指す「future, dedicated issue」を満たす）。

### 前提 issue（depends_on）

- **Issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run`
  （`commit_sha` 冪等キー・`kind` = JobType 値・`created_at` 時系列）と `repo_file` 共有テーブル、pgvector 拡張。
  本 issue は `analysis_run.commit_sha` で重複 run を抑止し、`created_at` 時系列から `debt_trend_point` を導出する。
- **Issue 028** `docs/issue/028-backend-code-debt-detection-pipeline.md` — `JobType.CODE_DEBT_DETECTION` /
  `code_debts`（`code_debt_score`）/ enqueue ルート。巡回で起動する analyze 系の 1 つ、`trend.code_debt_score` の素。
- **Issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `JobType.KC_ANALYSIS` /
  `file_kc`（`knowledge_coverage` = KC(file)）。巡回で起動する analyze 系の 1 つ、`trend.knowledge_coverage` の素。
- **Issue 030** `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — `JobType.KNOWLEDGE_DEBT_DETECTION` /
  `knowledge_debts`。巡回で起動する analyze 系の 1 つ。
- **Issue 031** `docs/issue/031-backend-overview-and-debt-registry-api.md` — `debt_trend_point` テーブル新設
  （`shared/shared/models/debt_trend_point.py`、`(project_id, week)` ユニーク）と **読み取り配信**。
  本 issue はその **書き込み**（週次スナップショット生成）を所有する。
- **Issue 017** `docs/issue/017-terraform-gcp-infrastructure.md` — GCP Terraform 基盤（Cloud Run api/service /
  Cloud Tasks / Cloud SQL / Secret Manager / WIF / bootstrap）。本 issue は 017 が将来送りにした
  Pub/Sub / Functions / Scheduler を **同じ命名・WIF・Secret 規約で追記**する。

> 本 issue は新しい解析ロジックも配信 API も作らない。**028-030 の既存パイプラインを「定期に・冪等に」起動する
> 巡回層**と、**031 の `debt_trend_point` の書き手**を追加するだけである。

### 独自性（他 issue との差分）

026-036 がデータモデル・解析・配信のいずれかを所有するのに対し、本 issue は **唯一の「定期実行 / インフラ」issue**
であり、(a) 017 が意図的に欠いた Pub/Sub / Functions / Scheduler を Terraform に表現する、(b) 巡回 enqueue の
**冪等性・頻度・コスト制御**という運用設計を確定する、(c) 031 が読み取り専用で残した `debt_trend_point` の
**書き込み（週次スナップショット集計）** を担う、という 3 点で性質が異なる。解析スコア式・KC 式・配信レスポンス形は
一切触らない。

## データモデル（新規 / 変更）

本 issue は **新規 ORM テーブルを作らない**。`debt_trend_point` は **Issue 031 が既に新設**しているため
（`shared/shared/models/debt_trend_point.py`、`(project_id, week)` ユニーク、`id` / `project_id` FK / `week` /
`code_debt_score` / `knowledge_coverage` / `created_at`）、本 issue はその **書き込み（upsert）** のみを行う。

- **Alembic 変更なし。** `debt_trend_point` テーブルの DDL は 031 が所有。本 issue は行を書くだけ
  （`on_conflict_do_update` で `(project_id, week)` を更新、`stack_analysis.py` の upsert 雛形に倣う）。
- **書き込み主体:** 週次スナップショット生成は service の **新パイプライン** または **Cloud Function 内**で行う
  （後述「パイプライン・非同期」で線引きを確定）。いずれも shared モデルへ DML する規約
  （`from shared.models import DebtTrendPoint, AnalysisRun`、薄い `service/service/db.py` セッション）に従う。
- **集計元:** `analysis_run`（026）の `created_at` を ISO 週で束ね、その週に完了した run に紐づく
  `code_debts.code_debt_score`（028）・`file_kc.knowledge_coverage`（029）を project 単位で平均し、
  `debt_trend_point.code_debt_score` / `.knowledge_coverage` に書く。`week` のラベル形は `debtTrendPointSchema.week`
  （`schemas.ts:190`、ISO 週 or ラベル）に合わせ、本 issue で正規形（例 ISO 週 `2026-W25`）を確定する。

> 028-030 のテーブル（`code_debts` / `file_kc` / `knowledge_debts`）の具体カラム名は各 issue の最終形に合わせる
> （捏造しない）。本 issue は集計の **読み手**であり、それらの DDL は変更しない。

## API（`/api/v1/...`）

**本 issue は api の公開エンドポイントを追加しない。** 巡回 enqueue は Cloud Function が api 内部の
`enqueue_job`（`backend/api/app/services/job_orchestrator.py:29`）相当を呼ぶか、Cloud Function 自身が
Cloud Tasks へ直接 enqueue する（後述で方式を確定）。配信 API（`GET .../overview` の `trend`）は **031 が所有**し、
本 issue が書いた `debt_trend_point` をそのまま読むだけで実時系列化される（schemas / client の変更不要）。

参考（本 issue が起動する既存の手動 enqueue ルート、変更しない）：

- `POST /api/v1/orgs/{slug}/projects/{project_slug}/detect-debts` → `202 {job_id}`（028、`JobType.CODE_DEBT_DETECTION`）
- `POST .../analyze-kc` → `202`（029、`JobType.KC_ANALYSIS`）
- `POST .../detect-knowledge-debts` → `202`（030、`JobType.KNOWLEDGE_DEBT_DETECTION`）

いずれも `stack.py::analyze_stack`（`backend/api/app/api/v1/stack.py:105-143`、方式 B = `installation_id` のみ
ペイロードに載せ `enqueue_job`）と同型。巡回層は **同じ payload 形・同じ `enqueue_job`** を再利用する。

## パイプライン・非同期

### 巡回スキャンの起動経路（Cloud Scheduler → Pub/Sub → Cloud Functions）

CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub トリガー）」に従い、017 の将来注記
（`docs/issue/017-...:161-166` の「Pub/Sub → Cloud Functions も選択肢」）どおり **Pub/Sub → Cloud Functions** を
採用する：

```
Cloud Scheduler (cron, 例: 毎週月曜 03:00 JST)
   └─ publish ─▶ Pub/Sub topic: <project_name>-<environment>-periodic-scan
                    └─ Eventarc/push ─▶ Cloud Function (2nd gen, internal)
                                          1) projects を列挙（Cloud SQL / api 内部）
                                          2) project ごとに最新 commit_sha を解決（方式 B token mint）
                                          3) analysis_run に同 commit_sha があれば skip（冪等）
                                          4) 無ければ analyze 系 Job を enqueue_job 経由で Cloud Tasks へ
                                          5) （週次バウンダリで）debt_trend_point スナップショットを upsert
```

- **Cloud Function の実体配置:** Function コードは backend の uv workspace に **`functions` メンバー**として追加するか、
  既存 service の薄いユーティリティを再利用する。enqueue は **api と同じ `enqueue_job`** を呼べるよう、
  `job_orchestrator` / `TaskDispatcher` / Cloud SQL セッションを Function ランタイムから利用する
  （015/016 の workspace 構成に追従。`app_ref/services/pyproject.toml` の `members = [..., "functions"]` が前例）。
- **冪等（同 commit_sha 抑止）:** Function は project ごとに最新 `commit_sha`（GitHub の default branch HEAD）を取り、
  `analysis_run`（026）に `(project_id, commit_sha, kind)` の完了 run があれば **enqueue しない**。
  これにより無変更リポジトリへの重複解析を抑止し、コストを抑える（026 が用意した冪等キーの本利用）。
- **頻度・コスト制御（変数化）:** スキャン cron（既定 週次）・1 回の巡回あたりの最大 project 数 /
  最大 enqueue 数・対象 analyze 種別（`code_debt_detection` / `kc_analysis` / `knowledge_debt_detection` の on/off）を
  Terraform 変数 + Function env で制御する。Cloud Tasks の `rate_limits`（017 `cloud-tasks.tf:14-17`）が
  下流のディスパッチ速度を律速するため、Function は enqueue するだけで実解析の並列度はキュー側で制御される。

### 週次スナップショット生成（`debt_trend_point` の書き込み）

`analysis_run` 時系列から週次の `code_debt_score` / `knowledge_coverage` を集計し `debt_trend_point` に upsert する。
書き込み主体は次の 2 案から確定する（本 issue で決定し、対象外・保留に判断を残す）：

- **案 1（推奨）: 専用パイプライン `trend_snapshot`。** `JobType.TREND_SNAPSHOT = "trend_snapshot"` を
  `shared/shared/enums.py:11` の `JobType` に追加（026 の命名規約 lowercase snake_case = queue/task path に従う）。
  `shared/shared/schemas/trend_snapshot.py` に `JobRequestBase` / `JobResultBase` 継承の Request/Result
  （`stack_analysis.py:58` 雛形、project_id / week を載せる）、
  `service/service/pipelines/trend_snapshot.py` の `process(request, ctx)` が `analysis_run` + `code_debts` +
  `file_kc` を集計し `ctx.session` で `debt_trend_point` を `on_conflict_do_update` upsert、
  `service/service/registry.py:15` の `PIPELINES` に三つ組登録。Cloud Function はこれを **enqueue するだけ**
  （巡回 analyze と同じ Cloud Tasks 経路に乗る・冪等・観測可能）。
- **案 2: Cloud Function 内で直接集計・直接 upsert。** Cloud SQL セッションを Function 内で開き
  `debt_trend_point` を直接書く。経路は短いが、解析は service・集計は Function とロジックが分散する。

> 推奨は **案 1**：解析と集計をどちらも「service の pipeline 三つ組 + Cloud Tasks enqueue」に揃え、Function を
> 「Scheduler 駆動の薄い enqueuer」に限定できる（観測・リトライ・冪等を既存基盤に委ねられる）。

### 既存基盤の再利用（新キューを作らない）

- enqueue は `enqueue_job`（`job_orchestrator.py:29`、QUEUED 永続化 → 90KB 超で GCS spill → `TaskDispatcher.dispatch`）を
  そのまま使う。analyze 系 payload は 028-030 と同形（方式 B = `GitHubRef.installation_id`）。
- service 側の `/tasks/{pipeline}` ・ `shared.worker.run_task`（冪等書き戻し）・registry 三つ組は 016/018 のまま。
  本 issue は **registry に `trend_snapshot` を 1 本足す**（案 1 採用時）だけで、analyze 系（028-030）は既登録を使う。

## タスク

### infra（`infra/gcp/`）

- [ ] `infra/gcp/apis.tf:7-24` の `for_each` に `pubsub.googleapis.com` / `cloudfunctions.googleapis.com` /
      `cloudscheduler.googleapis.com` / `eventarc.googleapis.com` を追加（017 が `:4-6` で「将来 issue」とした分）。
- [ ] `infra/gcp/pubsub.tf`（新設）— `google_pubsub_topic`（`name = "${var.project_name}-${var.environment}-periodic-scan"`）。
      Cloud Scheduler が publish、Cloud Function が購読する定期スキャン専用トピック（オンライン経路の result には使わない＝
      017 の「Pub/Sub をオンライン経路から排除」方針は不変）。
- [ ] `infra/gcp/cloud-scheduler.tf`（新設）— `google_cloud_scheduler_job`（`schedule = var.scan_cron`、`time_zone`、
      `pubsub_target { topic_name = google_pubsub_topic.periodic_scan.id, data = base64(...) }`）。cron は変数
      `var.scan_cron`（既定 週次、例 `"0 3 * * 1"`）。
- [ ] `infra/gcp/cloud-functions.tf`（新設）— `google_cloudfunctions2_function`（2nd gen、Eventarc トリガで
      上記 topic を購読、`ingress_settings = ALLOW_INTERNAL_ONLY`）。`service_account_email =
      google_service_account.scanner.email`、Cloud SQL 接続 + Secret Manager 参照（`GITHUB_APP_PRIVATE_KEY`）、
      env は 016/017 の `Settings` 名（`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `TASKS_QUEUE` /
      `JOB_PAYLOAD_BUCKET` / `SERVICE_TASKS_URL` / `DATABASE_URL`、`docs/issue/017-...:355-362` 対応表）と
      巡回制御 env（`SCAN_MAX_PROJECTS` / `SCAN_PIPELINES` 等）を注入。image は `var.container_image_functions`。
- [ ] `infra/gcp/iam.tf` — `google_service_account.scanner`（Function ランタイム SA）を追加し、`local.runtime_sas` と
      同様に `roles/cloudsql.client`（projects 列挙・`analysis_run` 参照・`debt_trend_point` 書込）/
      `roles/cloudtasks.enqueuer`（analyze・trend_snapshot Job 投入）/ `roles/aiplatform.user`（commit 解決時の
      方式 B は token mint のみ・AI 不要なら省略可）/ `roles/logging.logWriter` を付与。`infra/gcp/iam.tf:5-6` の
      「No Pub/Sub SA/no functions SA」コメントを本 issue で更新（scanner SA を追加した旨）。
- [ ] `infra/gcp/secrets.tf` — scanner SA に `github-app-private-key`（方式 B token mint 用）と `db-password` /
      `database-url` の `roles/secretmanager.secretAccessor` を限定付与（既存 api/service と同パターン）。
- [ ] `infra/gcp/variables.tf:215-217` のコメントを更新し、`container_image_functions`（image URI、スタブ default）/
      `scan_cron`（既定 `"0 3 * * 1"`）/ `scan_time_zone`（既定 `"Asia/Tokyo"`）/ `scan_max_projects` /
      `scan_pipelines`（list、既定 `["code_debt_detection","kc_analysis","knowledge_debt_detection"]`）を追加。
- [ ] `infra/gcp/outputs.tf` — `periodic_scan_topic` / `scanner_function_name` を追加。
- [ ] `infra/gcp/environments/stg.tfvars` / `prod.tfvars` — `scan_cron` / `scan_max_projects` の env 別上書き
      （stg は頻度低め・上限小、prod は週次）。

### infra（`infra/bootstrap/gcp/`）

- [ ] `infra/bootstrap/gcp/roles.tf:9-22` の `deploy_roles` に `roles/pubsub.admin` / `roles/cloudfunctions.admin` /
      `roles/cloudscheduler.admin` を追加（`:5-7` の「A future scheduled-scan issue adds them there.」を本 issue で実行）。
      Eventarc 用に `roles/eventarc.admin` も必要なら追記。
- [ ] `infra/bootstrap/gcp/apis.tf` — bootstrap が deploy 時に上記リソースを作れるよう、必要なら API を追記
      （多くは app スタックの `apis.tf` で有効化されるため、bootstrap 側は最小で可）。

### shared（`backend/shared/shared/`）— 案 1（`trend_snapshot` パイプライン）採用時

- [ ] `shared/shared/enums.py:11` の `JobType` に `TREND_SNAPSHOT = "trend_snapshot"` を追加
      （026 命名規約 = lowercase snake_case = queue/task path `trend-snapshot`）。
- [ ] `shared/shared/schemas/trend_snapshot.py` を新設（`JobRequestBase` / `JobResultBase` 継承、`stack_analysis.py:58`
      雛形。Request に `project_id` / `week`、Result に集計済み `code_debt_score` / `knowledge_coverage`）。
- [ ] `debt_trend_point` モデルは **031 が所有**（`shared/shared/models/debt_trend_point.py`）のため新設しない。
      本 issue は `from shared.models import DebtTrendPoint, AnalysisRun` で参照するのみ。

### service（`backend/service/service/`）— 案 1 採用時

- [ ] `service/service/pipelines/trend_snapshot.py` の `process(request, ctx)` を実装
      （`stack_analysis.py` の `process` / `on_conflict_do_update` 雛形 `:222`。`analysis_run`（026）を週で束ね、
      `code_debts`（028）/ `file_kc`（029）を project 単位平均、`ctx.session` で `debt_trend_point` を
      `(project_id, week)` upsert）。
- [ ] `service/service/registry.py:15` の `PIPELINES` に
      `JobType.TREND_SNAPSHOT.value: (TrendSnapshotRequest, TrendSnapshotResult, trend_snapshot.process)` を追記。

### functions（`backend/functions/` 新設 or 既存再利用）

- [ ] 巡回 Cloud Function 本体を新設（uv workspace に `functions` メンバー追加、`app_ref/services/pyproject.toml` の
      `members = [..., "functions"]` 前例）。Pub/Sub メッセージ受信 → projects 列挙 →
      project ごとに最新 `commit_sha` 解決（方式 B token mint）→ `analysis_run`（026）で同 commit 完了 run を確認し
      **無ければ** analyze 系を `enqueue_job` で投入 → 週次バウンダリで `trend_snapshot` を enqueue（案 1）。
- [ ] enqueue は `backend/api/app/services/job_orchestrator.py:29` の `enqueue_job` を共有
      （payload 形は `stack.py:125-134` の方式 B = `installation_id` のみ）。新キューは作らず 016/017 の Cloud Tasks に乗る。
- [ ] `docker/` に functions 用 Dockerfile（または Cloud Functions 2nd gen のソースデプロイ）を追加し、
      deploy workflow（Issue 025 系）が image を `var.container_image_functions` に注入できる枠を用意する。

### frontend（`frontend/src/`）

- [ ] **変更なし。** Overview の `trend` 配信は 031 の `GET .../overview` が所有し、本 issue が書いた
      `debt_trend_point` を読むだけで実時系列化される（`client.getOverview` / `overviewSchema` は不変）。

### test

- [ ] service（`backend/service/tests/`）— 案 1 採用時：`trend_snapshot.process` が `analysis_run` + `code_debts` +
      `file_kc`（モック投入）から週次平均を算出し `debt_trend_point` を `(project_id, week)` upsert すること。
      再実行（at-least-once）で二重行にならない冪等性。
- [ ] functions（`backend/functions/tests/`）：巡回ロジックが (a) `analysis_run` に同 `commit_sha` 完了 run が
      あれば enqueue しないこと（冪等）、(b) 無ければ `scan_pipelines` の各 analyze 系を `enqueue_job`（モック）で
      投入すること、(c) `SCAN_MAX_PROJECTS` で上限が効くこと。GitHub token は **方式 B**（service/Function が mint、
      ペイロードに `installation_id` のみ）であること。
- [ ] infra：`cd infra/gcp && terraform validate` と `terraform plan -var-file=environments/stg.tfvars` /
      `... prod.tfvars` がスタブ image で通ること。`cd infra/bootstrap/gcp && terraform validate` / `plan` が通ること。
      Pub/Sub topic / Scheduler job / Cloud Function / scanner SA + 追加ロールがすべて plan に現れること。

## 完了条件

- `infra/gcp/` に **Cloud Scheduler → Pub/Sub topic → Cloud Functions（2nd gen, internal）** の定期スキャン経路が
  記述され、`terraform validate` / `plan -var-file=environments/{stg,prod}.tfvars` がスタブ image で通ること。
- `infra/gcp/apis.tf` に `pubsub` / `cloudfunctions` / `cloudscheduler` / `eventarc` の有効化が追加され、
  `infra/bootstrap/gcp/roles.tf` の deploy SA に `roles/pubsub.admin` / `roles/cloudfunctions.admin` /
  `roles/cloudscheduler.admin`（+ 必要なら eventarc）が付与されていること（017 の「future issue」コメントを実行）。
- 巡回 Cloud Function が **各 project を列挙**し、`analysis_run.commit_sha`（026）で **同 commit の重複 run を抑止**しつつ
  analyze 系 Job（`code_debt_detection` / `kc_analysis` / `knowledge_debt_detection`）を **既存 `enqueue_job`（016/017 の
  Cloud Tasks）経由**で enqueue すること（新キューを作らない）。スキャン頻度・上限・対象種別が変数で制御できること。
- `analysis_run` 時系列から **週次の `debt_trend_point` が生成（upsert）** され、Issue 031 の `GET .../overview` の
  `trend` が **実時系列で返る**（空配列でなくなる）こと。`(project_id, week)` で冪等。
- GitHub token が **方式 B**（`installation_id` のみ搬送、service/Function が Secret Manager から mint）で、
  Pub/Sub メッセージ・Function env に **平文の秘密が載らない**こと。WIF（long-lived 鍵不使用）で deploy できること。
- バックエンド（案 1 採用時）: `cd backend && uv run ruff check shared/shared api/app service/service` /
  `uv run ruff format --check ...` / `uv run ty check ...` / `uv run --directory service pytest`（+ functions/shared）が通ること。
- `CHANGELOG.md`（日本語, Keep a Changelog）に `Added`（定期スキャン基盤：Cloud Scheduler/Pub-Sub/Cloud Functions +
  巡回 enqueue + `debt_trend_point` 週次スナップショット生成）を追記。

## 対象外・保留

- **解析ロジック本体**（git 履歴解析・重複/dead/複雑度・AI 生成痕跡・KC 算出・Gemini）— Issue 028 / 029 / 030 が所有。
  本 issue は既存パイプラインを「定期に・冪等に」起動するだけ。
- **配信 API**（`GET .../overview` の `trend` 読み取り含む）— Issue 031 が所有。本 issue は `debt_trend_point` の
  書き込みのみ。client / schemas の変更はしない。
- **`debt_trend_point` テーブルの DDL / Alembic** — Issue 031 が新設済み。本 issue は行を upsert するだけ
  （マイグレーション追加なし）。
- **週次スナップショットの書き込み主体**（案 1 専用パイプライン vs 案 2 Function 直書き）— 本 issue で **案 1（専用
  `trend_snapshot` パイプライン）を推奨・採用**する判断を上記に記載。実装時に最終確定する。
- **deploy workflow への配線**（functions image のビルド/push）— Issue 025 系（GCP CI/CD）の follow-up で
  `var.container_image_functions` に注入する枠だけ用意。
- **pgvector による埋め込み類似検索の本実装**（重複検知・概念マッピング）— 将来 issue。pgvector 拡張は
  Issue 026 で有効化済みだが本利用は本 issue の責務外。
- **Pub/Sub をオンライン経路（result 通知）に使うこと** — 017 の「result は service の Cloud SQL 直接書き込み」
  方針は不変。本 issue の Pub/Sub は **定期スキャン専用トピック**であり、ジョブ結果の搬送には使わない。
- **Cloud Scheduler → HTTP 直叩き方式**（017 注記の第一候補）— 本 issue は Pub/Sub → Functions を採用。HTTP 直叩きは
  将来の最適化として保留。

## 参考

- 関連 issue
  - `docs/issue/017-terraform-gcp-infrastructure.md` — GCP Terraform 基盤。`apis.tf:4-6` / `iam.tf:5-6` /
    `variables.tf:215-217` / `bootstrap/gcp/roles.tf:5-7` の「将来 issue で追加」コメントが本 issue の起点
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run`（`commit_sha` 冪等キー・
    `created_at` 時系列）/ `repo_file`（`:100,208` が「037 が同 commit の重複 run 抑止に使う」と明記）
  - `docs/issue/028-...` / `029-...` / `030-...` — `JobType.CODE_DEBT_DETECTION` / `KC_ANALYSIS` /
    `KNOWLEDGE_DEBT_DETECTION` と analyze 系 enqueue ルート（巡回で起動する対象）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — `debt_trend_point` 新設 + 読み取り配信
    （`:118-120,303` が「書き込みは 037」と明記）。本 issue はその書き手
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — pipeline 三つ組・enqueue（202）・registry の様式の正典
- 既存 infra（追記対象・踏襲元）
  - `infra/gcp/apis.tf:4-24`（API 有効化、pubsub/functions/scheduler/eventarc を追加）/ `cloud-tasks.tf:8-27`
    （巡回が乗る既存キュー・rate_limits）/ `iam.tf:1-63`（SA トポロジ、scanner SA を追加）/
    `variables.tf:163-217`（task/scan 変数）/ `secrets.tf` / `outputs.tf` / `environments/{stg,prod}.tfvars`
  - `infra/bootstrap/gcp/roles.tf:1-30`（deploy SA ロール、pubsub/functions/scheduler admin を追加）/ `apis.tf`
- 既存 backend（雛形・流用）
  - `backend/api/app/services/job_orchestrator.py:29`（`enqueue_job` = QUEUED 永続化 → GCS spill → dispatch）
  - `backend/service/service/registry.py:15`（pipeline 三つ組登録、`trend_snapshot` を追記）
  - `backend/service/service/pipelines/stack_analysis.py:222`（`on_conflict_do_update` upsert 雛形）/
    `process` 雛形
  - `backend/shared/shared/enums.py:11`（`JobType`、`TREND_SNAPSHOT` を追記）/ `JobStatus`（`analysis_run.status` 整合）
  - `backend/shared/shared/schemas/stack_analysis.py:58`（`JobRequestBase` / `JobResultBase` / `GitHubRef` = 方式 B）
  - `backend/api/app/api/v1/stack.py:105-143`（方式 B enqueue 雛形、`installation_id` のみ payload）/
    `backend/api/app/api/v1/github.py:92-133`（`resolve_installation_id` / `InstallationIdDep`、commit/installation 解決）
  - `backend/api/app/models/project.py:31-34`（`repo_owner` / `repo_name` / `default_branch` = 巡回対象の素）
  - `app_ref/services/pyproject.toml`（`members = [..., "functions"]` = functions メンバー追加の前例）
- フロント契約（本 issue が実時系列化する）
  - `frontend/src/lib/api/schemas.ts:189-193`（`debtTrendPointSchema` = `week` / `code_debt_score` /
    `knowledge_coverage`）/ `:202-208`（`overviewSchema.trend`）
  - `frontend/src/lib/mock/overview-mock.ts`（`trend` モック形の参照）
- 規約
  - `CLAUDE.md` — 「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub）」/ Secret Manager 必須 /
    Vertex AI + ADC（google-api-key 不使用）/ WIF / 方式 B / `models/__init__.py` import 順（app→shared）/
    JobType 命名規約（lowercase snake_case = queue path）/ ゲート（`uv run ruff` / `ty` / `pytest`、
    `terraform validate` / `plan`）/ `CHANGELOG.md`（日本語, Keep a Changelog）
