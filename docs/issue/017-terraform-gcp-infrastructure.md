# GCP 版 Terraform を新設する（infra/gcp + infra/bootstrap/gcp）

## 概要

現状 `infra/` には `azure/`・`aws/`・`bootstrap/{azure,aws}/` の 3 クラウド分の Terraform が
あるが、**CLAUDE.md が必須プラットフォームとして掲げる Google Cloud Platform の構成が存在しない**。
本 issue では `infra/gcp/`（アプリスタック）と `infra/bootstrap/gcp/`（CI 用 WIF + tfstate）を新設し、
issue-015 で確定する **api / service の 2 コンテナ構成** と issue-016 が定める
**Cloud Tasks による非同期タスク基盤（request ディスパッチ + service の Cloud SQL 直接書き込みによる result）** を、
GCP マネージドサービスでプロビジョンする。

`infra/azure` と `infra/aws` の既存規約 — `terraform >= 1.11`、環境ごとの `environments/*.tfvars`、
bootstrap での **WIF → GitHub environment ピン留め**、tfstate を別 prefix/key へ分離、
`project_name` / `environment` / `region_short` の命名、`database-url` / `secret-key` などの
Secret 命名 — をそのまま踏襲する。差分は、**AI が Vertex AI（ADC）であるため `google-api-key`
Secret を原則作らない**点（azure/aws との明確な違い）と、**api / service の 2 サービス + Cloud Tasks キュー +
両サービスからの Cloud SQL アクセス + 外部 HTTPS LB + Cloud Armor**を新規に持つ点である
（定期スキャン用の Cloud Functions / Cloud Scheduler は本 issue スコープ外。後述の将来注記を参照）。

## 背景・目的

### 現状

| クラウド | アプリスタック | bootstrap | tfstate backend | コンテナ実行 |
|---|---|---|---|---|
| Azure | `infra/azure/` | `infra/bootstrap/azure/` | `azurerm`（`key=fullstack-app.tfstate` / `bootstrap.tfstate`） | Container Apps（1 サービス） |
| AWS | `infra/aws/` | `infra/bootstrap/aws/` | `s3`（`fullstack-app/terraform.tfstate` / `.../bootstrap/...`） | ECS Express Mode（1 サービス） |
| **GCP** | **なし** | **なし** | **なし** | **なし** |

既存 2 クラウドはいずれも **単一コンテナ**（`var.container_image` 1 つ）を実行するだけで、
worker / キュー / Job モデルの概念を持たない。これは現行 `backend/` が単一 FastAPI モノリスで
あることの素直な反映である（`backend/app/core/config.py` の `Settings` にもキューやジョブの
設定は存在しない）。

Rosetta の方向性は **api コンテナ と service コンテナ への分割**であり、重い処理（ADK スタック解析等）を
service 側で非同期実行する（issue-018）。この構成を GCP で動かすための Terraform が本 issue の対象である。

### 目的

1. **GCP を一級のデプロイ先にする。** CLAUDE.md のインフラ章のうち本 issue スコープ
   （Cloud Run / Cloud SQL / Secret Manager / Artifact Registry / WIF / Cloud Armor /
   Cloud Logging+Monitoring+Trace）を Terraform に落とす。CLAUDE.md が挙げる Cloud Functions
   （定期スキャン・Pub/Sub トリガー）は定期スキャン専用であり、定期スキャン自体が本 issue 群（015–018）の
   スコープ外のため、ここでは作らない（後述の将来注記を参照）。
2. **api / service の 2 Cloud Run + Cloud Tasks + 両サービスからの Cloud SQL アクセス** を、azure/aws の
   命名・環境分離・WIF 規約と整合する形で記述する（result は service の DB 直接書き込みで、Pub/Sub は使わない）。
3. **bootstrap で WIF を GitHub environment にピン留め**し、long-lived 鍵を一切使わずに
   `google-github-actions/auth` から `terraform apply` できる土台を作る（follow-up の deploy workflow で利用）。

### 前提 Issue（depends_on）

- **015** `docs/issue/015-backend-api-service-split-monorepo.md` — バックエンドを api/service に分割
  （uv workspace モノレポ化）。本 issue がプロビジョンする **2 つの Cloud Run サービス**の構成（コンテナ名
  `api` / `service`、`backend/` を workspace ルートとする方針、`docker/api.Dockerfile` /
  `docker/service.Dockerfile`）は 015 の確定に従う。
- **016** `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks による
  api→service 非同期タスク基盤 + Job ライフサイクル + GCS スピルオーバー。result は service が
  Cloud SQL の `Job` 行を直接更新する方式（api へのコールバック無し、フロントは `GET /api/v1/jobs/{job_id}` を
  ポーリング）。本 issue がプロビジョンする **Cloud Tasks の request キュー、両サービスからアクセスする
  Cloud SQL、GCS payload バケット、Cloud Tasks の宛先 `/tasks/{pipeline}`** は 016 の設計に一致させる。

> 015/016 が未マージの段階でも、本 issue の Terraform は**スタブ image（`gcr.io/cloudrun/hello` 等の
> プレースホルダ）と空のキュー定義**で `terraform validate` / `plan` を通せる構造にする。実 image は
> deploy workflow（follow-up）が `var.container_image_api` / `var.container_image_service` に注入する。

### 独自性（azure/aws の単純コピーにしない）

既存 2 クラウドは「1 コンテナ + DB + Secret + レジストリ」止まりだが、GCP 版は **point-to-point の
タスクディスパッチ（Cloud Tasks）+ service による Cloud SQL への結果直接書き込み**を初めて
インフラに表現する。参考実装 `app_ref/services/worker/worker/broker.py` は Azure Queue Storage を
request / result の 2 本に分けて使う（`_queue_name` / `_result_queue_name`）が、GCP 版は result 経路を
**専用キュー/トピックに分けず、service が処理完了後に直接 DB を更新する**ことで簡素化する。GCP では：

- **request（api→service）= Cloud Tasks** — マネージドな「タスクキュー」で、HTTP ターゲット
  （service の `/tasks/{pipeline}`）へ OIDC 認証付きで点対点ディスパッチ。リトライ・バックオフ・
  レート制御・重複排除が組み込みで、参考実装の request キューに最も近い。
- **result（service の Cloud SQL 直接書き込み）** — service の `/tasks/{pipeline}` ハンドラが処理完了後、
  自前の DB セッションで `Job` 行を `COMPLETED`/`FAILED` + `result_data` に更新する（api へのコールバックや
  Pub/Sub push は無し）。フロントは `GET /api/v1/jobs/{job_id}` をポーリングするだけ。そのため
  **service Cloud Run にも Cloud SQL 接続 + `DATABASE_URL` が必要**で、これが「1 コンテナ + DB」の
  azure/aws と最も異なる点になる。`Job` モデルは `shared` パッケージに置き api/service 双方が参照、
  Alembic マイグレーションと DB エンジン生成は api が所有する（015/016 の確定）。

本設計は **request=Cloud Tasks / result=Cloud SQL 直接書き込み**を採用し、Pub/Sub をオンライン経路から
完全に排除する。理由は本節と `## 技術詳細` のキュー構成図に明記する。

## タスク

### `infra/gcp/`（アプリスタック）

#### 基盤・プロバイダ

- [ ] `main.tf` — `terraform >= 1.11`、`required_providers` に `google` / `google-beta`（`hashicorp/google`,
      `~> 6.x`）。`backend "gcs"`（`bucket = "<project_name>-tfstate"`, `prefix = "gcp/"`）。
      `locals`：`db_name = replace(var.project_name, "-", "_")`、`region_short`
      （`asia-northeast1 => an1` / `asia-northeast2 => an2` / `us-central1 => uc1`、fallback は
      `replace(var.region, "-", "")`）。`provider "google"` / `provider "google-beta"` に
      `project = var.gcp_project_id` / `region = var.region` / `default_labels`
      （`project` / `environment` / `managed-by = terraform`）。
- [ ] `apis.tf` — `google_project_service` で必須 API を有効化（`for_each` の toset）：
      `run.googleapis.com`, `cloudtasks.googleapis.com`,
      `sqladmin.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`,
      `cloudbuild.googleapis.com`,
      `compute.googleapis.com`, `vpcaccess.googleapis.com`, `iam.googleapis.com`,
      `iamcredentials.googleapis.com`, `aiplatform.googleapis.com`, `logging.googleapis.com`,
      `monitoring.googleapis.com`, `cloudtrace.googleapis.com`。
      `disable_on_destroy = false`（共有プロジェクトでの破壊防止）。
      **`pubsub.googleapis.com` / `cloudfunctions.googleapis.com` / `cloudscheduler.googleapis.com` /
      `eventarc.googleapis.com` は本 issue では有効化しない**（オンライン経路に Pub/Sub は無く、
      定期スキャン用の Functions/Scheduler は将来の専用 issue で導入する。後述の将来注記を参照）。

#### コンテナ実行とレジストリ

- [ ] `artifact-registry.tf` — `google_artifact_registry_repository`（`format = "DOCKER"`,
      `repository_id = "${var.project_name}-${var.environment}"`, `location = var.region`）。
      api / service の image を同一リポジトリ配下にタグで分ける（定期スキャン用 functions image は本 issue では作らない）。
- [ ] `cloud-run.tf` — `google_cloud_run_v2_service` を 2 つ：
  - `api` — `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`（外部公開は LB 経由のみ）。
    `template.service_account = google_service_account.api.email`、Secret Manager 参照
    （`env { value_source { secret_key_ref {...} } }`）で `SECRET_KEY` / `GITHUB_APP_PRIVATE_KEY` /
    `GITHUB_CLIENT_SECRET` / `GITHUB_WEBHOOK_SECRET` / `DATABASE_URL`（または DB パスワード）を注入、
    平文 env は **issue-016 の `Settings` キー名と 1:1 で一致させる**（下表参照）：`ENVIRONMENT` /
    `COOKIE_SECURE=true` / `GOOGLE_CLOUD_PROJECT`（既存 `config.py`。Vertex AI と Cloud Tasks で共用）/
    `GOOGLE_CLOUD_LOCATION`（同上。リージョンを共用）/ `TASKS_QUEUE` /
    `JOB_PAYLOAD_BUCKET` / `SERVICE_TASKS_URL`（= service の URL）等のみ。**Terraform が注入する env キー名は
    016 の `Settings` フィールド名と完全一致させること**（不一致だと app が読めない。canonical 名は 016 を正とし、
    `## 技術詳細` の「Cloud Run 注入 env ↔ 016 Settings 対応表」で 1:1 を担保）。Cloud SQL 接続
    （`volumes { cloud_sql_instance { instances = [...connection_name] } }`）。api は Alembic マイグレーションと
    DB エンジン/セッション生成を所有する（`api/app/core/db.py`）。`cpu` / `memory` /
    `min_instance_count` / `max_instance_count` / `timeout` は変数化。
  - `service` — `ingress = INGRESS_TRAFFIC_INTERNAL_ONLY`（Cloud Tasks からのみ起動）。
    高 CPU/メモリ・長 `timeout`（最大 3600s 系）。`template.service_account =
    google_service_account.service.email`。**service も Cloud SQL 接続 + `DATABASE_URL`（Secret Manager 参照）を
    必ず注入する** — service は `/tasks/{pipeline}` ハンドラの処理完了後に自前の薄い `service/service/db.py`
    （engine/session）で `shared` の `Job` 行を `COMPLETED`/`FAILED` + `result_data` に直接更新するため
    （マイグレーションは実行せず、DML のみ）。同様に Secret / Vertex AI も付与。
  - 共通：`vpc_access { connector = google_vpc_access_connector.main.id, egress = ... }`（Cloud SQL private IP /
    内部通信用）。`google_cloud_run_v2_service_iam_member` で **service には `roles/run.invoker` を
    Cloud Tasks 用 SA（`tasks_invoker`）にのみ付与**し（Cloud Tasks → service の OIDC ディスパッチ用）、
    `allUsers` は決して付けない（外部到達は LB+Armor 経由の api だけ）。
- [ ] `cloud-tasks.tf` — `google_cloud_tasks_queue` をパイプライン単位（最低 1 本：`stack-analysis`、
      `for_each` で `var.task_pipelines` を展開可能に）。`rate_limits`
      （`max_dispatches_per_second` / `max_concurrent_dispatches`）、`retry_config`
      （`max_attempts` / `min_backoff` / `max_backoff` / `max_doublings`）を変数で調整。
      キューは service の `/tasks/{pipeline}` を HTTP ターゲットにする（宛先 URL / OIDC は api 側コードが
      enqueue 時に指定するため、ここではキュー本体のみ定義）。

#### result の取り扱い（Pub/Sub を使わない）

result はオンライン経路では **service が Cloud SQL の `Job` 行を直接更新**することで反映する
（`cloud-run.tf` の service 定義を参照）。したがって本 issue では **`pubsub.tf` を作らない**
（job-results トピック / dead-letter トピック / scheduled-scan トピック / push subscription /
DLQ subscription / Pub/Sub push 用 SA はいずれも不要）。result 通知用のインフラリソースは存在しない。

- [ ] **失敗・DLQ 代替（アプリ層）** — Cloud Tasks にネイティブ DLQ は無く、Pub/Sub DLQ も使わないため、
      失敗は **`Job(status=FAILED, error, payload)` として Cloud SQL に残す**（再 enqueue 可能）。さらに api 側に
      **stale-job タイムアウト掃除**（app_ref の `result_poller._timeout_stale_jobs` 相当：`PROCESSING` のまま
      放置された Job を `FAILED` 化）を置く。これらはアプリ実装（015/016）の責務で、インフラ側に専用リソースは
      不要だが、本 .tf 群に Pub/Sub DLQ を作らない根拠としてここで明記する。

> **将来注記（定期スキャン）:** 定期スキャン（自律エージェントの定期再スキャン）は将来の専用 issue で実装。
> 起動は **Cloud Scheduler → HTTP（Cloud Run/Functions を OIDC で直叩き）を第一候補**、仕様書
> （`仕様書.md` §974「毎週・毎日エージェントが自律的に動く」/ §355「30 日後の再スキャン」/ §801
> 「Cloud Functions｜定期スキャン｜Pub/Sub トリガー」）準拠で **Pub/Sub → Cloud Functions** も選択肢。
> **本 issue では `cloud-functions.tf` / `cloud-scheduler.tf` を作らない**（必要なら将来 issue で最小スタブから
> 追加）。それに伴い `cloudfunctions`/`cloudscheduler`/`pubsub`/`eventarc` の API 有効化も本 issue では行わない。

#### データ・ストレージ・秘密

- [ ] `database.tf` — `google_sql_database_instance`（`database_version = "POSTGRES_17"`,
      `region = var.region`, `settings { tier / disk_size / backup_configuration /
      database_flags { name="cloudsql.enable_google_ml_integration" or pgvector availability note } }`）。
      pgvector は Cloud SQL PG17 で `CREATE EXTENSION vector` で利用可能（拡張の有効化はマイグレーション側、
      ここでは PG17 + 接続経路を用意）。`ip_configuration`：**prod は private IP（`private_network` +
      VPC connector）**、**staging は `ipv4_enabled = true` + `authorized_networks` で簡素化**
      （azure/aws の staging が public access を許す方針に倣う）。`deletion_protection =
      var.environment == "prod"`。`google_sql_database`（`name = local.db_name`）、`google_sql_user`
      （`name = var.db_username`, `password = var.db_password`）。
- [ ] `storage.tf` — `google_storage_bucket.job_payloads`
      （`name = "${var.project_name}-${var.environment}-job-payloads"`,
      `uniform_bucket_level_access = true`, `lifecycle_rule`（短期 TTL で削除）, `versioning` 任意）。
      Cloud Tasks の body サイズ上限を超える **request** payload の spillover 先（`gs://` 参照 = 参考実装の
      `blob://` 相当の `$requestRef`。result は service が Cloud SQL に直書きするため spillover しない）。api / service の runtime SA に
      `roles/storage.objectAdmin` をこのバケット限定で付与。
- [ ] `secrets.tf` — `google_secret_manager_secret` + `google_secret_manager_secret_version` を
      `secret-key` / `github-app-private-key` / `github-client-secret` / `github-webhook-secret` /
      `db-password`（または `database-url`）について作成。**`google-api-key` は作らない**
      （AI は Vertex AI + ADC のため。`backend/app/core/config.py` は `GOOGLE_CLOUD_PROJECT` /
      `GOOGLE_CLOUD_LOCATION` を使い API キーを持たない）。各 runtime SA（api/service）に
      `google_secret_manager_secret_iam_member`（`roles/secretmanager.secretAccessor`）を**必要な
      Secret だけ**付与。

#### ネットワーク・公開・エッジ

- [ ] `networking.tf` — `google_compute_network`（custom mode）+ `google_compute_subnetwork` +
      `google_vpc_access_connector`（Serverless VPC Access、Cloud Run → Cloud SQL private IP /
      内部通信用）。prod は private service access（`google_service_networking_connection`）を併設。
      **staging は簡素化可**（コメントで明示、azure の `networking.tf` の「Simplified networking」スタンスに倣う）。
- [ ] `load-balancer.tf` — external global HTTPS LB：`google_compute_region_network_endpoint_group`
      （`network_endpoint_type = "SERVERLESS"`, `cloud_run { service = api }`）、
      `google_compute_backend_service`（`security_policy = google_compute_security_policy.armor.id` を紐付け）、
      `google_compute_url_map` → `google_compute_target_https_proxy` → `google_compute_global_forwarding_rule`、
      `google_compute_managed_ssl_certificate`（`var.domain`、未指定時は `google_compute_global_address` +
      自己署名/省略で plan が通る形）。
- [ ] `cloud-armor.tf` — `google_compute_security_policy`（backend service にアタッチ）。
      `compose.prod.yml` の Traefik レート制限を**等価ルール**として移植：
      `/api/v1/auth/login` = 5/min・10/hour、`/api/v1/auth/refresh` = 30/min（送信元 IP 単位、
      `rate_limit_options` の `enforce_on_key = "IP"` + `ban_threshold`/`rate_limit_threshold`）。
      CLAUDE.md が「レート制限 = Cloud Armor（エッジで強制）」を必須とする。
      Pub/Sub push 受信エンドポイントは存在しない（result は service の Cloud SQL 直接書き込み）ため、
      **`/internal/*` を Pub/Sub push 送信元 CIDR に限定するルールは不要**で、`var.pubsub_push_source_ranges` も
      作らない。

#### 監視・IAM・入出力

- [ ] `monitoring.tf` — `google_logging_metric`（log-based metric：5xx 率や job 失敗ログ）、
      `google_monitoring_uptime_check_config`（LB の `api_url` への HTTPS uptime check）、
      `google_monitoring_alert_policy`（uptime 失敗 / エラーレート閾値）。Cloud Run の stdout/stderr は
      Cloud Logging に自動取込されるため、ログシンクの明示は不要（azure の Log Analytics 接続に相当する
      手当ては GCP では既定で済む旨をコメント）。
- [ ] `iam.tf` — runtime / dispatcher の SA を集約定義：
      `google_service_account.api` / `.service` / `.tasks_invoker`。
      最小権限バインディング：両 runtime SA に `roles/cloudsql.client`（**api/service とも Cloud SQL へ接続** —
      api はマイグレーション + 通常クエリ、service は `Job` 行の直接更新）、`roles/aiplatform.user`
      （Vertex AI、**google-api-key 不要の根拠**）、`api` に `roles/cloudtasks.enqueuer`（タスク投入）、
      `tasks_invoker` に service の `roles/run.invoker`（`cloud-run.tf` 側で member 付与、Cloud Tasks → service の
      OIDC ディスパッチ用）。**Pub/Sub 関連の SA / ロール（`pubsub_push` SA、`roles/pubsub.publisher` 等）と
      `functions` SA は作らない**（オンライン経路に Pub/Sub は無く、定期スキャン用 Functions は本 issue スコープ外）。
      Secret / Storage の限定バインドは各 .tf に置きつつ、SA 本体と project レベルロールはここで一望できるようにする。
- [ ] `variables.tf` — `project_name`（default `fullstack-app`）, `environment`, `gcp_project_id`,
      `region`（default `asia-northeast1`）, `db_username`（sensitive, default `postgres`）,
      `db_password`（sensitive）, `secret_key`（sensitive）, `github_app_private_key`（sensitive）,
      `github_client_secret`（sensitive）, `github_webhook_secret`（sensitive）,
      `container_image_api` / `container_image_service`（image URI）,
      per-service の `api_cpu`/`api_memory`/`api_min_instances`/`api_timeout` と
      `service_cpu`/`service_memory`/`service_min_instances`/`service_timeout`,
      `db_tier` / `db_disk_size` / `db_backup_enabled`, `task_pipelines`（list）, `domain`（任意）。
      **`google_api_key` 変数は作らない**（azure/aws との差分）。**`pubsub_push_source_ranges` /
      `container_image_functions` も作らない**（Pub/Sub push 受信なし、定期スキャン Functions は本 issue スコープ外）。
- [ ] `outputs.tf` — `artifact_registry_repo`, `api_url`（LB の HTTPS エンドポイント）, `service_url`
      （internal）, `db_connection_name`（sensitive）, `job_payloads_bucket`, `tasks_queue_names`。
      （Pub/Sub を使わないため `job_results_topic` 出力は無い。）
- [ ] `terraform.tfvars.example`、`environments/stg.tfvars`、`environments/prod.tfvars`
      （cpu/mem/min-instances/backup/db_tier の env 上書き。prod は大きめ + private IP + deletion_protection,
      staging は小さめ + public DB。azure/aws の `environments/*.tfvars` と同じ粒度）。

### `infra/bootstrap/gcp/`（CI 用 WIF + tfstate）

- [ ] `main.tf` — `terraform >= 1.11`、`provider "google"`、`backend "gcs"`
      （`bucket = "<project_name>-tfstate"`, `prefix = "gcp/bootstrap/"` — アプリスタックの
      `prefix = "gcp/"` と分離し相互ロックを避ける。azure の `bootstrap.tfstate` / aws の
      `.../bootstrap/...` と同じ分離思想）。`data "google_project" "current"`。
- [ ] `apis.tf` — bootstrap が必要とする最小 API：`iam.googleapis.com`, `iamcredentials.googleapis.com`,
      `sts.googleapis.com`, `cloudresourcemanager.googleapis.com`, `storage.googleapis.com`,
      `serviceusage.googleapis.com`。
- [ ] `state.tf` — `google_storage_bucket`（tfstate 用、`versioning { enabled = true }`,
      `uniform_bucket_level_access = true`, `force_destroy = false`）。**鶏卵問題の注記**：この bucket は
      bootstrap が作るが、bootstrap 自身の backend も同 bucket を指す。初回のみローカル backend で apply →
      `terraform init -migrate-state` で GCS backend へ移す手順をコメントに明記（aws の
      「`use_lockfile` + 共有 bucket」, azure の「同 container 別 key」の鶏卵対処に相当）。
- [ ] `wif.tf` — `google_iam_workload_identity_pool` + `google_iam_workload_identity_pool_provider`
      （GitHub OIDC：`issuer_uri = "https://token.actions.githubusercontent.com"`,
      `attribute_mapping`（`google.subject = assertion.sub`, `attribute.repository = assertion.repository`,
      `attribute.environment` 等）, `attribute_condition` で
      `assertion.repository == "<owner>/<repo>"` に制限）。`google_service_account.github_deploy`。
      `google_service_account_iam_member`（`roles/iam.workloadIdentityUser`）を
      **`principalSet://.../attribute.repository/<owner>/<repo>` かつ environment を
      `repo:<owner>/<repo>:environment:staging|production` 相当にピン留め**（`for_each = var.environments`）。
      azure の federated credential（`subject = repo:.../:environment:<env>`）/ aws の OIDC trust
      （`token...:sub = repo:.../:environment:<env>`）と等価な environment ピン留めにする。
- [ ] `roles.tf` — deploy SA の project レベルロール（concern 別に整理、aws の scoped deploy policy の
      最小権限思想に倣う）：`roles/run.admin`, `roles/cloudtasks.admin`,
      `roles/cloudsql.admin`, `roles/secretmanager.admin`, `roles/artifactregistry.admin`,
      `roles/iam.serviceAccountAdmin` + `roles/iam.serviceAccountUser`（actAs：runtime SA を Cloud Run に
      割り当てるため）, `roles/storage.admin`（tfstate / payload bucket）, `roles/compute.admin`
      （LB / Cloud Armor / VPC）, `roles/serviceusage.serviceUsageAdmin`（API 有効化）,
      `roles/iam.workloadIdentityPoolAdmin`（必要時）。
      **`roles/pubsub.admin` / `roles/cloudfunctions.admin` / `roles/cloudscheduler.admin` は付与しない**
      （本 issue でこれらのリソースを作らないため。定期スキャン用 Functions/Scheduler を将来 issue で追加する際に
      その issue 側で追記する）。
- [ ] `variables.tf` — `repo_owner`, `repo_name`, `gcp_project_id`, `region`（default `asia-northeast1`）,
      `project_name`（default `fullstack-app`）, `environments`（default `["staging","production"]`）,
      `state_bucket`。
- [ ] `outputs.tf` — `workload_identity_provider`（フル resource name、GitHub vars `GCP_WIF_PROVIDER` に貼付）、
      `deploy_service_account_email`（GitHub vars `GCP_DEPLOY_SA` に貼付）。azure の `client_id` /
      aws の `role_arn` と同じ「GitHub vars 貼付用」役割。

### follow-up（本 issue では枠/言及のみ）

- [ ] `.github/workflows/deploy-stg-gcp.yml` / `deploy-prod-gcp.yml` を別 issue で追加。
      `google-github-actions/auth`（`workload_identity_provider` + `service_account`、long-lived 鍵なし）で
      WIF 認証 → Artifact Registry へ push（api/service image）→ `terraform apply -var-file`。
      prod は GitHub environment の required reviewers でゲート（azure/aws の deploy workflow と同じ流儀）。

## 完了条件

- `infra/bootstrap/gcp/` で `terraform init`（GCS backend）/ `terraform validate` /
  `terraform plan` が通ること（初回は鶏卵対処手順どおりローカル backend → migrate でも可）。
- `infra/gcp/` で `terraform init` / `terraform validate` / `terraform plan -var-file=environments/stg.tfvars`
  と `... -var-file=environments/prod.tfvars` が、スタブ image（または注入 image）で通ること。
- 以下が**すべて**プロビジョン対象として記述されていること：
  - Cloud Run **api**（ingress=internal-LB）+ **service**（ingress=internal-only, 高 cpu/mem・長 timeout、**Cloud SQL 接続 + `DATABASE_URL`**）
  - **Cloud Tasks** キュー（パイプライン単位、rate/retry 設定）+ tasks SA + service への `roles/run.invoker`
  - **Cloud SQL PostgreSQL 17**（pgvector 利用可能経路、prod=private IP / staging=public+authorized。**api/service の両方が接続**）
  - **Artifact Registry**（Docker）、**Secret Manager**（`google-api-key` を含まない）、**GCS** payload バケット
  - **WIF**（GitHub environment ピン留め）、**Cloud Armor + 外部 HTTPS LB**、**監視**（log-based metric / uptime / alert）
- **オンライン経路に Pub/Sub リソースが一切無いこと**（job-results / dead-letter / scheduled-scan トピック、
  push/DLQ subscription、Pub/Sub push 用 SA、`pubsub.googleapis.com` API、`RESULTS_TOPIC` env、
  `roles/pubsub.*` が `infra/gcp/` に存在しない）。result は service の Cloud SQL 直接書き込み、失敗・DLQ は
  アプリ層の `Job(status=FAILED)` + stale-job 掃除で代替。
- **定期スキャン用の Cloud Functions / Cloud Scheduler は本 issue では作らない**（将来の専用 issue で
  Scheduler→HTTP 第一候補 / Pub/Sub→Functions 選択肢として実装）。
- 命名（`project_name`/`environment`/`region_short`）・`environments/*.tfvars` の env 分離・
  bootstrap の **WIF → GitHub environment ピン留め**・tfstate の **別 prefix（`gcp/` vs `gcp/bootstrap/`）**が
  azure/aws と整合していること。
- **プレーンテキストの秘密が一切ないこと**（すべて Secret Manager 参照、sensitive 変数、`.tfvars` に平文秘密を置かない）。
- AI 認証が **Vertex AI + ADC**（runtime SA に `roles/aiplatform.user`）で、`google-api-key` Secret/変数を
  作っていないこと（azure/aws との差分が `secrets.tf` / `variables.tf` のコメントに明記されていること）。
- `roles.tf` の deploy ロールが concern 別に整理され、`roles/iam.serviceAccountUser`（actAs）が
  含まれていること（Cloud Run への runtime SA 割り当てに必須）。

## 技術詳細

### GCP ↔ Azure ↔ AWS サービス対応表

| 役割 | GCP（本 issue） | Azure（`infra/azure`） | AWS（`infra/aws`） |
|---|---|---|---|
| api コンテナ | Cloud Run service `api`（ingress=internal-LB） | Container App（1 本） | ECS Express Mode（1 本） |
| service（重い処理 worker） | Cloud Run service `service`（ingress=internal-only） | —（無し） | —（無し） |
| request キュー（api→service） | **Cloud Tasks** → service `/tasks/{pipeline}`（OIDC） | —（参考実装は Azure Queue request） | —（無し） |
| result（service→DB） | **service が Cloud SQL の `Job` 行を直接更新**（コールバック/Pub/Sub 無し。フロントは `GET /api/v1/jobs/{job_id}` をポーリング） | —（参考実装は Azure Queue result） | —（無し） |
| 失敗・DLQ | アプリ層：`Job(status=FAILED)` 永続化 + api の stale-job 掃除（再 enqueue 可） | —（無し） | —（無し） |
| 定期スキャン | （オンライン経路では不使用。将来の定期スキャンで Cloud Scheduler→HTTP もしくは Pub/Sub→Cloud Functions を検討。本 issue では作らない） | —（無し） | —（無し） |
| payload spillover | **GCS** バケット（`gs://` = `$requestRef`。request のみ。result は Cloud SQL 直書き） | —（参考実装は `blob://`） | —（無し） |
| DB | Cloud SQL PostgreSQL 17（pgvector） | PostgreSQL Flexible Server 17（VECTOR ext） | RDS PostgreSQL 17 |
| コンテナレジストリ | Artifact Registry（Docker） | ACR（admin 無効・UAMI pull） | ECR（scan on push） |
| 秘密 | Secret Manager（`google-api-key` 無し） | Key Vault（`google-api-key` 有り） | Secrets Manager（`google-api-key` 有り） |
| ランタイム ID | per-service SA + `roles/aiplatform.user` | UAMI（AcrPull + KV Secrets User） | ECS task/exec/infra roles |
| エッジレート制限 | Cloud Armor（外部 HTTPS LB 上） | —（compose.prod の Traefik 相当） | —（compose.prod の Traefik 相当） |
| CI 認証 | WIF（pool + provider, environment ピン留め） | UAMI + federated credential | OIDC provider + assume-role |
| tfstate backend | GCS（`gcp/` / `gcp/bootstrap/`） | azurerm（`fullstack-app.tfstate` / `bootstrap.tfstate`） | s3（`.../terraform.tfstate` / `.../bootstrap/...`） |
| 監視 | Cloud Logging + Monitoring + Trace（自動取込） | Log Analytics workspace | CloudWatch Logs group |

> AI 行が GCP だけ「`google-api-key` 無し」になるのが azure/aws との最大の差分。既存コード
> （`backend/app/core/config.py`）は `GOOGLE_CLOUD_PROJECT` + ADC を使い、`GOOGLE_API_KEY` を持たない。
> よって runtime SA に `roles/aiplatform.user` を付ければ十分で、Secret は不要。

### Cloud Run 注入 env ↔ 016 Settings 対応表（1:1 で揃える）

Terraform（`cloud-run.tf`）が注入する平文 env のキー名は、**issue-016 の `Settings`
（`backend/.../core/config.py`）フィールド名と完全一致**させる。canonical 名は **016 を正**とし、
本 issue はそれに追随する（016 側を 017 名へ改名するのではなく、017 の注入名を 016 名へ合わせる合意。
両 issue にこの方針を明記する）。

| 役割 | 注入 env キー（= 016 Settings 名） | Terraform 値の出どころ | 注入先 |
|---|---|---|---|
| プロジェクト ID（Vertex AI / Cloud Tasks で共用） | `GOOGLE_CLOUD_PROJECT` | `var.gcp_project_id` | api / service |
| ロケーション（Vertex AI / Cloud Tasks で共用） | `GOOGLE_CLOUD_LOCATION` | `var.region` | api / service |
| request キュー名 | `TASKS_QUEUE` | `google_cloud_tasks_queue.*.name`（pipeline 単位、016 の既定 `job-requests`） | api |
| spillover バケット | `JOB_PAYLOAD_BUCKET` | `google_storage_bucket.job_payloads.name`（= `<project_name>-<environment>-job-payloads`） | api / service |
| Cloud Tasks の HTTP ターゲット | `SERVICE_TASKS_URL` | service Cloud Run の URL（`google_cloud_run_v2_service.service.uri`） | api |
| DB 接続文字列（Secret Manager 参照） | `DATABASE_URL` | `google_secret_manager_secret_version.database_url`（または `db-password` から組み立て） | **api / service の両方**（service も `Job` 行を直接更新するため必須） |

> `RESULTS_TOPIC` は廃止（result は service の Cloud SQL 直接書き込みで、Pub/Sub トピックを使わない）。
> 代わりに **`DATABASE_URL` を api / service の両方へ注入**する点が本構成の要点（016 でも同様）。

> **注意（不一致の罠）:** app（016 の `Settings`）が読む env キー名と Terraform が注入するキー名が
> 1 文字でも違うと app は値を読めずクラッシュする。canonical 名は上表のとおり **016 を正**とし、017 は
> それに完全一致させる。特に **プロジェクト ID とロケーションは新規キーを作らず、既存 `config.py` の
> `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` を Vertex AI と Cloud Tasks で共用**する
> （`GCP_PROJECT` や `CLOUD_TASKS_LOCATION` のような別名は作らない）。`JOB_PAYLOAD_BUCKET` の値は 017 の
> Terraform 命名規約（`<project_name>-<environment>-job-payloads`）を正とし、016 もこの命名・キー名へ揃える。

**リージョン方針（統一）:** インフラ（Cloud Run / Cloud SQL / Cloud Tasks）と Vertex AI の
リージョンは **`var.region`（既定 `asia-northeast1`）に一本化**する。すなわち Terraform は `GOOGLE_CLOUD_LOCATION`
に `var.region`（= `asia-northeast1`）を注入し、Cloud Tasks の親パスにも同じリージョンを使う。既存 `config.py` の
`GOOGLE_CLOUD_LOCATION` 既定 `us-central1` は**ローカル既定値にすぎず**、本番では Terraform 注入で上書きされる
（016 / 017 / 既存 config の三者を `asia-northeast1` で揃える。Vertex AI が当該リージョンで対象モデルを提供する
ことを前提とし、未提供のモデルを使う場合のみ Vertex 用に別リージョンを変数で切り出す）。

### キュー構成図（request=Cloud Tasks / result=Cloud SQL 直接書き込み）

```
                         ┌───────────────────────────── external HTTPS LB ─────────────────────────────┐
   client ──HTTPS──▶ Cloud Armor (rate limit) ──▶ serverless NEG ──▶ Cloud Run: api (ingress=internal-LB)
                                                                          │  ▲
            (1) enqueue task  ──────────────────────────────────────────▶│  │ (4) GET /api/v1/jobs/{job_id}
                                                                          │  │     をフロントがポーリング
                                                                          ▼  │
                                        Cloud Tasks ──HTTP(OIDC: tasks_invoker SA)──▶ Cloud Run: service
                                        /tasks/{pipeline}                              (ingress=internal-only)
                                                                                            │
                       (2) 重い処理 (ADK 解析等) を実行。大きい I/O は GCS へ spill         │
                                                                                            ▼
                                            (3) service が自前 DB セッションで Job 行を
                                                COMPLETED/FAILED + result_data に直接更新
                                                                                            │
   ┌────────────────────────── Cloud SQL (PostgreSQL 17) ────────────────────────────┐    │
   │  Job テーブル（shared.models.Job）: api が読み取り/作成 + Alembic 所有,          │◀───┘
   │                                     service が完了時に直接 UPDATE（DML のみ）     │
   └──────────────────────────────────────────────────────────────────────────────────┘
        ▲ api も Cloud SQL 接続（マイグレーション + 通常クエリ + ポーリング応答）

   spillover:    request が上限超過 → GCS bucket *-job-payloads に退避, メッセージに $requestRef（result は Cloud SQL 直書きのため spillover 無し）
   失敗・DLQ:    service が Job(status=FAILED, error, payload) を残す（再 enqueue 可）+ api が stale-job を掃除
   ※ Pub/Sub はオンライン経路に存在しない。定期スキャンは将来の専用 issue（Scheduler→HTTP / Pub/Sub→Functions）。
```

参考実装 `app_ref/services/worker/worker/broker.py` は `request_queue` / `result_queue` の 2 本構成で、
`kick()` が request へ送信、`publish_result()` が result へ送信するが、GCP 版は **result 側のキュー/トピックを
持たず、service が Cloud SQL の `Job` 行を直接更新する**ことで簡素化する。request 側のみ Cloud Tasks
（point-to-point の HTTP ディスパッチ）を使い、Cloud Run のゼロスケールと OIDC ディスパッチに乗せる。
`blob://container/path`（`app_ref/services/shared/shared/blob.py` の `parse_blob_url`）に相当する spillover
参照は GCP では `gs://bucket/object`。

### service が Cloud SQL に result を直接書き込む経路

result は service の `/tasks/{pipeline}` ハンドラが処理完了後に **自前の薄い `service/service/db.py`（engine /
session）で `shared` の `Job` 行を直接 UPDATE**する（`COMPLETED`/`FAILED` + `result_data`、ドメイン結果も）。
api へのコールバックや Pub/Sub push は介在しない。これにより以下がインフラ要件になる：

- **service Cloud Run に Cloud SQL 接続 + `DATABASE_URL` を注入**（`cloud-run.tf`）。service の runtime SA に
  `roles/cloudsql.client`（`iam.tf`）。マイグレーションは api が所有し、service は DML のみ（テーブル作成は
  しない）。`Job` モデルは `shared.models.Job`（SQLModel）で api/service 双方が `from shared.models import Job`。
- **冪等性**（Cloud Tasks は at-least-once）：service は処理前に `Job.status` を確認し、既に `COMPLETED` なら
  スキップ／upsert する（アプリ実装 015/016 の責務、インフラ側に追加リソース不要）。
- **失敗・DLQ 代替**：Pub/Sub DLQ は使わず、失敗を `Job(status=FAILED, error, payload)` として Cloud SQL に
  残し再 enqueue 可能とする。加えて api 側に **stale-job タイムアウト掃除**（`PROCESSING` のまま放置された Job を
  `FAILED` 化、app_ref の `result_poller._timeout_stale_jobs` 相当）を置く。

> まとめ：result 経路に外部到達エンドポイント（旧 `/internal/jobs/results`）も Pub/Sub も存在しない。フロントは
> `GET /api/v1/jobs/{job_id}` をポーリングして進捗・結果を取得する。インフラ上は **api / service の両方が同じ
> Cloud SQL を共有**する点だけが追加要件となる。

### Cloud Armor ルール表（compose.prod.yml の Traefik 対比）

| 対象パス | Traefik（`compose.prod.yml`） | Cloud Armor（`cloud-armor.tf`） |
|---|---|---|
| `/api/v1/auth/login` | `average=5, period=1m, burst=5` ＋ `average=10, period=1h, burst=10` | `rate_limit_options`：1m 窓 5 req/IP・1h 窓 10 req/IP、`enforce_on_key = "IP"`、超過は `deny(429)` |
| `/api/v1/auth/refresh` | `average=30, period=1m, burst=30` | `rate_limit_options`：1m 窓 30 req/IP、`enforce_on_key = "IP"`、超過は `deny(429)` |
| その他 | デフォルト（明示制限なし） | default rule `allow`（必要なら全体の throttle を追加） |

> Pub/Sub push 受信エンドポイント（旧 `/internal/jobs/results`）が無くなったため、`/internal/*` を push 送信元
> CIDR に限定する Cloud Armor ルールも不要（`var.pubsub_push_source_ranges` も作らない）。

> Cloud Armor の `rate_limit_options` は単一 window の閾値しか持たないため、login の「分 + 時」二段は
> `expr`（`request.path.matches('/api/v1/auth/login')`）でマッチした優先度違いの 2 ルール（分用・時用）に
> 分割して表現する。値は Traefik の token-bucket（average=burst）と等価に揃える。

### `infra/gcp` + `infra/bootstrap/gcp` ファイルツリー

```
infra/
  gcp/
    main.tf                  # terraform>=1.11, google/google-beta ~>6.x, backend gcs(prefix=gcp/), locals
    apis.tf                  # google_project_service 一括有効化
    artifact-registry.tf     # Docker repository
    cloud-run.tf             # api(internal-LB, Cloud SQL) + service(internal-only, Cloud SQL) + tasks run.invoker
    cloud-tasks.tf           # queue (pipeline 単位, rate/retry)
    # （Pub/Sub は無し。result は service の Cloud SQL 直接書き込み）
    # （cloud-functions.tf / cloud-scheduler.tf も無し。定期スキャンは将来の専用 issue）
    database.tf              # Cloud SQL PG17 (pgvector), db, user — api/service 両方が接続
    storage.tf               # *-job-payloads spillover bucket
    secrets.tf               # secret-key/github-*/db-password（google-api-key 無し）
    networking.tf            # VPC + subnet + Serverless VPC connector（staging 簡素化可）
    load-balancer.tf         # external HTTPS LB + serverless NEG → api + managed cert
    cloud-armor.tf           # security policy（Traefik 等価レート制限）
    monitoring.tf            # log-based metric / uptime check / alert policy
    iam.tf                   # api/service/tasks_invoker SA + 最小権限（Pub/Sub/functions SA なし）
    variables.tf
    outputs.tf
    terraform.tfvars.example
    environments/
      stg.tfvars
      prod.tfvars
  bootstrap/
    gcp/
      main.tf                # backend gcs(prefix=gcp/bootstrap/), provider, data google_project
      apis.tf                # iam/iamcredentials/sts/cloudresourcemanager/storage/serviceusage
      state.tf               # GCS tfstate bucket（versioning, UBLA）+ 鶏卵注記
      wif.tf                 # WIF pool/provider（GitHub OIDC, env ピン留め）+ github_deploy SA
      roles.tf               # deploy SA project ロール（concern 別）
      variables.tf
      outputs.tf
```

### WIF subject ピン留めの説明

azure / aws は **GitHub environment**（branch ではなく environment）に subject をピン留めし、
production を required reviewers でゲートする：

- azure（`infra/bootstrap/azure/federated.tf`）:
  `subject = "repo:${var.repo_owner}/${var.repo_name}:environment:${each.value}"`
- aws（`infra/bootstrap/aws/role.tf`）:
  `token.actions.githubusercontent.com:sub = "repo:.../:environment:${e}"`

GCP も同じ意味論を WIF で表現する。`google_iam_workload_identity_pool_provider` の
`attribute_mapping` で `attribute.repository = assertion.repository` /
`attribute.environment = assertion.environment` を持たせ、`attribute_condition` で
`assertion.repository == "<owner>/<repo>"` に絞る。さらに deploy SA への
`roles/iam.workloadIdentityUser` を `for_each = var.environments` で
`principalSet://iam.googleapis.com/${pool}/attribute.environment/<env>`（repository 制約と AND）に
バインドし、**environment 単位**で許可する。これにより production environment の required reviewers が
そのまま GCP デプロイのゲートになる（long-lived 鍵は一切発行しない）。

### Cloud Run の 2 サービス分割（issue-015 / 016 との対応）

```
docker/api.Dockerfile      → image → Cloud Run api      (ingress=internal-LB, /api/v1/*, /api/v1/jobs/{job_id})
docker/service.Dockerfile  → image → Cloud Run service  (ingress=internal-only, /health, /tasks/{pipeline})
```

- 両サービスとも Cloud SQL に接続する（api：マイグレーション + 通常クエリ + `GET /api/v1/jobs/{job_id}` の
  ポーリング応答、service：`Job` 行の完了時 UPDATE）。result 用の push 受信エンドポイントは無い。
- コンテナ名は issue-015 が確定する **`api` / `service`**（参考実装の `worker` 相当が `service`）。
- `backend/` を uv workspace ルートとする 015 の方針に従い、Dockerfile はマルチステージ uv workspace
  ビルド（`app_ref/services/api/Dockerfile` / `worker/Dockerfile` の `uv sync --frozen --no-dev
  --package ...` を踏襲）。本 issue は image URI を `var.container_image_api` /
  `var.container_image_service` で受け取るだけで、ビルドは deploy workflow（follow-up）が担う。
- service は外部到達不可（`INGRESS_TRAFFIC_INTERNAL_ONLY` + `run.invoker` を Cloud Tasks 用 SA（`tasks_invoker`）限定）。
  api だけが外部 HTTPS LB の背後で公開される。

### 環境別 tfvars（azure/aws 同等の粒度）

```hcl
# infra/gcp/environments/stg.tfvars（例）
environment        = "stg"
api_cpu            = "1"
api_memory         = "512Mi"
api_min_instances  = 0
service_cpu        = "2"
service_memory     = "2Gi"
service_min_instances = 0
db_tier            = "db-f1-micro"
db_backup_enabled  = false
# staging は Cloud SQL public IP + authorized networks（simplified networking）

# infra/gcp/environments/prod.tfvars（例）
environment        = "prod"
api_cpu            = "2"
api_memory         = "1Gi"
api_min_instances  = 1
service_cpu        = "4"
service_memory     = "4Gi"
service_min_instances = 0
db_tier            = "db-custom-2-7680"
db_backup_enabled  = true
# prod は Cloud SQL private IP + VPC connector, deletion_protection=true
```

> 秘密（`db_password` / `secret_key` / `github_*`）は `.tfvars` に書かず、CI から
> `-var` / `TF_VAR_*`（GitHub environment secrets）で注入する。azure/aws と同じく平文秘密は置かない。

## 参考

### 関連 Issue（相互参照）

- **015** `docs/issue/015-backend-api-service-split-monorepo.md` — api/service 分割（uv workspace モノレポ化）。
  本 issue の Cloud Run 2 サービス・Dockerfile 構成の前提。
- **016** `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks の非同期タスク基盤・
  Job ライフサイクル・GCS spillover（result は service の Cloud SQL 直接書き込み、Pub/Sub なし）。本 issue が
  プロビジョンする Cloud Tasks キュー / Cloud SQL / バケットと宛先パスの設計元。
- **018** `docs/issue/018-stack-analysis-async-job-on-service.md` — ADK スタック解析を service へ移し非同期化。
  本 issue が用意する service Cloud Run + Cloud Tasks の最初の利用者。

### 既存 Terraform（踏襲元）

- `infra/azure/{main,variables,outputs,container-app,database,key-vault,acr,identity,networking,monitoring}.tf`、
  `infra/azure/environments/{stg,prod}.tfvars` — 命名・env 分離・Secret 参照・simplified networking の規約。
- `infra/aws/{main,variables,outputs,ecs,ecr,rds,networking}.tf` — `region_short` lookup・tag/命名・
  staging public DB・skip/deletion 保護の env 分岐。
- `infra/bootstrap/azure/{main,identity,federated,roles,variables,outputs}.tf` — WIF（federated credential）の
  environment ピン留め、tfstate 別 key、deploy ロールの per-concern 付与、GitHub vars 貼付用 outputs。
- `infra/bootstrap/aws/{main,oidc,role,variables,outputs}.tf` — OIDC provider + assume-role trust の
  environment ピン留め、scoped least-privilege deploy policy（concern 別 statement）、`role_arn` output。

### 参考実装（app_ref）

- `app_ref/services/worker/worker/broker.py` — request/result の 2 キュー構成（GCP では request 側のみ
  Cloud Tasks を採用し、result 側はキューを使わず service の Cloud SQL 直接書き込みに簡素化）。
- `app_ref/services/shared/shared/blob.py` — `blob://container/path` 参照（GCS の `gs://` spillover に対応）。
- `app_ref/services/api/Dockerfile` / `app_ref/services/worker/Dockerfile` — マルチステージ uv workspace ビルド。
- `app_ref/services/pyproject.toml` — `[tool.uv.workspace] members = ["shared","api","worker","functions"]`
  （本リポジトリは `backend/` を workspace ルートにし members を `shared`/`api`/`service` とする）。

### その他

- `CLAUDE.md` — インフラ章（Cloud Run / Cloud Functions / Cloud SQL / Secret Manager / Artifact Registry /
  WIF / Cloud Armor / Cloud Logging+Monitoring+Trace）と「プレーンテキスト環境変数は絶対不可」。
- `compose.prod.yml` — Traefik レート制限（`/auth/login` 5/min・10/hour、`/auth/refresh` 30/min）= Cloud Armor 移植元、
  `pgvector/pgvector:pg17` = Cloud SQL PG17 + pgvector の整合先。
- `backend/app/core/config.py` — `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`（Vertex AI / ADC、
  `GOOGLE_API_KEY` なし）= `google-api-key` Secret を作らない根拠、注入する env / Secret の一覧元。
```
