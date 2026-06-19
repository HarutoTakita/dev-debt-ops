# GitHub Actions に GCP デプロイ（WIF）を新設し CI/CD を有効化する

## 概要
GCP の Terraform（`infra/gcp` + `infra/bootstrap/gcp`）は整備済みだが、GitHub Actions が **GCP 非対応のまま**で、しかも `.github/` 全体が **未コミット（untracked）**のため CI/CD が一切起動しない。`.github/` をコミットしたうえで、WIF 認証で GCP に自動デプロイする再利用ワークフロー `deploy-gcp.yml` を新設し、`deploy-stg.yml` / `deploy-prod.yml` から呼び出す。あわせて、不要となった **AWS / Azure のインフラ（`infra/aws` `infra/azure` `infra/bootstrap/aws` `infra/bootstrap/azure`）とデプロイワークフロー（`deploy-aws.yml` `deploy-azure.yml` `build-image.yml`）を削除**し、デプロイ対象を GCP 単独に整理する。

## 背景・目的

### 現状（デプロイ不可の根拠）
- `.github/` 配下が **すべて untracked**（`git ls-files .github` が空）→ push / tag を打っても Actions は何も実行されない。**最大のブロッカー**。
- 旧 deploy 経路は **AWS / Azure 専用**で、GCP への配線が皆無だった（`deploy-stg.yml` / `deploy-prod.yml` は `deploy-aws.yml` / `deploy-azure.yml` のみを呼んでいた）。さらに `build-image.yml` が存在しない `docker/Dockerfile.prod` を参照しており AWS/Azure ビルド自体が壊れていた。
- 本プロジェクトのデプロイ対象は GCP 単独であり、AWS / Azure 構成は不要。

### 目的
- 不要な AWS / Azure のインフラ・ワークフローを削除し、構成を GCP 単独に単純化する。
- `.github/` をコミットして Actions を起動可能にする。
- 長期鍵を使わず **WIF のみ**で GCP に認証し、`develop` push で stg、`v*.*.*` tag で prod に **api / service 両 Cloud Run** を自動デプロイする。
- bootstrap（WIF プール / deploy SA / tfstate バケット）の outputs を GitHub の Variables / Secrets に橋渡しする手順を確立する。

### 前提 Issue（depends_on）
- #017 GCP 版 Terraform（`infra/gcp` + `infra/bootstrap/gcp`）— 本 issue はその follow-up（017 末尾「`deploy-*-gcp.yml` は別 issue」に対応）。
- #015 api / service コンテナ分割、#016 Cloud Tasks 非同期基盤（Cloud Run の env / secret 名はここに準拠）。

## タスク

### 0. 前提
- [ ] bootstrap（`infra/bootstrap/gcp`）を一度 apply 済みにする（WIF プール / プロバイダ / deploy SA / tfstate バケット）。未了なら本 issue 着手前に実施。

> **`.github/` のコミットは本 issue の実装をすべて終えてから一括で行う**（タスク 5 参照）。現状 `.github/` は untracked のため Actions が起動しないが、未完成の状態で先にコミットせず、GCP 対応一式が揃ってからまとめてコミットする。

### 1. AWS / Azure の削除
- [x] `infra/aws` / `infra/azure` / `infra/bootstrap/aws` / `infra/bootstrap/azure` を削除（いずれも未追跡）。
- [x] `.github/workflows/deploy-aws.yml` / `deploy-azure.yml` / `build-image.yml`（単一イメージビルド。AWS/Azure 専用）を削除。
- [x] `.github/dependabot.yml` の Terraform 対象を `/infra/aws` `/infra/azure`（+ bootstrap）から `/infra/gcp` `/infra/bootstrap/gcp` に差し替え。

### 2. `deploy-gcp.yml`（reusable: build + deploy 統合）
GCP は api / service の **2 サービス**構成で、Artifact Registry リポジトリを app スタック（`infra/gcp`）が所有するため、「イメージ push 前にリポジトリが無い」鶏卵問題がある。`gcloud` で先に作ると後続 apply が AlreadyExists で衝突するので、**Terraform がリポジトリを所有したまま `-target` で先行作成 → 2 イメージ build/push → 本 apply** の順を 1 ワークフローに統合する（当初案の `build-image-gcp.yml` 分離はこの理由で取りやめ）。
- [x] `workflow_call`、inputs: `environment`（GitHub Environment = `staging`/`production`、WIF の OIDC `environment` claim 用）/ `image_tag` / `tfvars_file`（Terraform env = `stg`/`prod`）。
- [x] secrets: `DB_PASSWORD` / `SECRET_KEY` / `GH_APP_PRIVATE_KEY` / `GH_CLIENT_SECRET` /（任意）`GH_WEBHOOK_SECRET`（`GITHUB_` 始まりは GitHub が禁止のため `GH_` プレフィックス。`TF_VAR_github_*` にマップ）。
- [x] `permissions: id-token: write`、`concurrency: gcp-deploy-${environment}`（GCS state ロック競合の直列化）。
- [x] `google-github-actions/auth@v2`（`vars.GCP_WIF_PROVIDER` / `vars.GCP_DEPLOY_SA`）+ `setup-gcloud` + `gcloud auth configure-docker`。
- [x] `terraform apply -target=google_artifact_registry_repository.main` で AR リポジトリ先行作成 → `api.Dockerfile` / `service.Dockerfile` を build/push → **Trivy で両イメージをスキャン**（CRITICAL/HIGH で fail）→ 本 `terraform apply`（`TF_VAR_container_image_api` / `_service` 注入）。
- [x] **Alembic マイグレーション**は api イメージ起動時に `alembic upgrade head`（`docker/api.Dockerfile`、advisory lock・冪等）で実行されるため、本 apply で完結（専用ステップ不要）。
- [x] ヘルスチェック：`api_url` が HTTPS（`var.domain` 設定時）または `vars.APP_URL` 設定時のみ `/api/v1/health` を実行。ドメイン未設定時（LB IP のみでリスナー無し）は warning で通知しデプロイは失敗させない。

### 3. stg / prod から呼び出し
- [x] `deploy-stg.yml`：`push develop` → `deploy-gcp.yml`（`environment: staging` / `image_tag: github.sha` / `tfvars_file: stg.tfvars`）。
- [x] `deploy-prod.yml`：`push tag v*.*.*`（`v0.0.x` を除外）→ `deploy-gcp.yml`（`environment: production` / `image_tag: github.ref_name` / `tfvars_file: prod.tfvars`）。

### 4. GitHub 側設定（手動・bootstrap outputs から）
- [ ] **Variables**：`GCP_WIF_PROVIDER`（= bootstrap output `workload_identity_provider`）/ `GCP_DEPLOY_SA`（= `deploy_service_account_email`）/ `GCP_PROJECT_ID` / `GCP_REGION`（既定 `asia-northeast1`）/（任意）`APP_URL`。
- [ ] **Secrets**：`DB_PASSWORD` / `SECRET_KEY` / `GH_APP_PRIVATE_KEY` / `GH_CLIENT_SECRET` /（任意）`GH_WEBHOOK_SECRET`。
- [ ] **Environments**（`staging` / `production`）を作成。bootstrap の WIF は `attribute.environment` で staging/production をピン留めしているため、GitHub Environment 名を一致させる（`wif.tf` の env バインディング参照）。

### 5. 反映（最後に一括）
- [ ] 上記をすべて終えてから、`.github/`（`ci` / `release` / `e2e` / 新規 `deploy-gcp.yml` + GCP 単独化した `deploy-stg` / `deploy-prod` + `dependabot.yml`）を **まとめてコミット＆プッシュ**する。これにより初めて Actions が起動する（未完成での先行コミットはしない）。
- [ ] CLAUDE.md / `docs/` の CI/CD 記述を GCP 単独・必要な Variables/Secrets 一覧に合わせて更新。

## 完了条件
- `.github/` が（GCP 対応一式を含めて）Git に commit 済みで、Actions が起動する。
- AWS / Azure のインフラ・ワークフローがリポジトリから無くなっている。
- `develop` に push すると stg の **api / service 両 Cloud Run** が新イメージで更新され、起動時マイグレーションが適用され、HTTPS エンドポイント設定時は `{api_url}/api/v1/health` が 200 を返す。
- `v*.*.*` tag（`v0.0.x` を除く）push で prod に同等のデプロイが走る。
- 認証は **WIF のみ**（long-lived な鍵/JSON を使用しない）。

## 技術詳細

### bootstrap output → GitHub 設定の対応表
| bootstrap output（`infra/bootstrap/gcp/outputs.tf`） | GitHub 設定 | 用途 |
|---|---|---|
| `workload_identity_provider` | Variable `GCP_WIF_PROVIDER` | `auth@v2` の `workload_identity_provider` |
| `deploy_service_account_email` | Variable `GCP_DEPLOY_SA` | `auth@v2` の `service_account` |
| `state_bucket` | （直接は不要） | `infra/gcp` の `backend "gcs"` が同バケットを参照（prefix `gcp/`） |
| —（手動） | Variable `GCP_PROJECT_ID` / `GCP_REGION` | `TF_VAR_gcp_project_id` / イメージ URI 構築 |

### 環境名の二重性（重要）
| 軸 | staging | production | 用途 |
|---|---|---|---|
| GitHub Environment（`environment:`） | `staging` | `production` | WIF の OIDC `environment` claim（bootstrap の principalSet バインディングと一致必須） |
| Terraform env（`-var-file`） | `stg.tfvars`（`environment="stg"`） | `prod.tfvars`（`environment="prod"`） | AR リポジトリ ID `fullstack-app-stg/-prod`、Cloud Run 名等 |

### Cloud Run への値注入（`infra/gcp/cloud-run.tf` 準拠）
| 種別 | 値 | 供給元 |
|---|---|---|
| イメージ | `container_image_api` / `container_image_service` | `deploy-gcp.yml` が build/push したURIを `TF_VAR_*` で注入 |
| plain env | `ENVIRONMENT` / `TASKS_QUEUE` / `TASKS_INVOKER_SA` / `JOB_PAYLOAD_BUCKET` / `SERVICE_TASKS_URL` 等 | Terraform が resource から自動解決 |
| secret env | `SECRET_KEY` / `GITHUB_CLIENT_SECRET` / `GITHUB_WEBHOOK_SECRET` / `DATABASE_URL` | Secret Manager（`secrets.tf`）。値は `TF_VAR_*`（`db_password` / `secret_key` / `github_*`）から apply 時に投入 |

> `DATABASE_URL` は Terraform が Cloud SQL 接続情報から Secret Manager（`database-url`）に格納し、Cloud Run が `value_source.secret_key_ref` で参照する。ワークフローが直接 DB URL を組み立てる必要はない。

### `deploy-gcp.yml` の処理順
1. WIF auth（`auth@v2`）→ `setup-gcloud` → `setup-terraform` → `terraform init`（backend は `gcs`、コミット済み）
2. `terraform apply -target=google_artifact_registry_repository.main`（AR リポジトリ先行作成。初回以降は no-op）
3. `terraform output -raw artifact_registry_repo` から repo ID を取得し、`${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/{api,service}:${TAG}` を構築
4. `gcloud auth configure-docker` → `api.Dockerfile` / `service.Dockerfile` を buildx で build & push（gha キャッシュ、scope 分離）
5. Trivy で両イメージスキャン（CRITICAL/HIGH で fail）
6. 本 `terraform apply`（`TF_VAR_container_image_api/_service` 注入）→ Cloud Run 更新 + api 起動時に DB マイグレーション
7. ヘルスチェック（HTTPS エンドポイント設定時のみ）

### マイグレーションの扱い
`docker/api.Dockerfile` の runtime CMD が `alembic upgrade head && exec uvicorn ...`（advisory lock・冪等）。GCP api リビジョン起動時にマイグレーションが走るため、ワークフローに専用段は不要。prod でマイグレーション失敗を serving リビジョンに波及させたくない場合のみ、migrate 専用 Cloud Run Job 方式を検討する（任意・別タスク化可）。

## 参考
- ワークフロー: `.github/workflows/{deploy-gcp,deploy-stg,deploy-prod,ci,release,e2e}.yml`、`.github/dependabot.yml`
- GCP infra: `infra/gcp/{cloud-run,artifact-registry,secrets,variables,outputs}.tf`、`infra/bootstrap/gcp/{wif,outputs,roles}.tf`
- 関連 Issue: #015（api/service 分割）, #016（Cloud Tasks）, #017（GCP Terraform）, #018（service 非同期ジョブ）
- 想定ラベル（GitHub issue 化時）: `infra`, `chore`
