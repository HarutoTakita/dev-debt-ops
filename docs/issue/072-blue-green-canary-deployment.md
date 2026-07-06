# ブルーグリーン / 段階カナリアデプロイの導入（Phase 0 + Phase 1）

## 概要

DevOps の一環として、Cloud Run に**無停止・低リスクなデプロイ**を導入する。新リビジョン（green）を
トラフィック 0% で先に起動し、段階的に（0% → 10% → 100%）切り替え、問題があれば旧リビジョン（blue）へ
即ロールバックする。ブルーグリーンと段階カナリアは Cloud Run 上で同一機構（green/blue リビジョン + トラフィック
分割 + 旧リビジョン保持）であり、本 issue はその中核を実現する。既定の切替カーブは**段階カナリア（0→10→100）**。

本 issue の対象は **Phase 0（マイグレーション分離 + expand-contract 規約）** と **Phase 1（段階カナリア）**。
監視シグナルによる自動ロールバック等は **Phase 2** として対象外。

## 背景・目的

- 現状のデプロイは `terraform apply` で Cloud Run の `image` を差し替える方式で、`traffic` ブロックを持たない
  ため**最新リビジョンへ 100% 即時切替**（ローリング）。カナリア/ブルーグリーンの制御性がない。
- **最大の障壁は DB**: api コンテナは起動時に `alembic upgrade head` を実行し（`docker/api.Dockerfile`
  runtime CMD）、Cloud SQL は**単一インスタンスを api / service が共有**する。green の起動で共有 DB の
  スキーマが変わると、まだ配信中の blue が壊れうる。→ green/blue の並走を安全にするには、
  (1) マイグレーションを起動から分離し、(2) スキーマ変更を後方互換（expand-contract）にする必要がある。
- deploy SA は `roles/run.admin` + `roles/iam.serviceAccountUser` を保有済み。`run.googleapis.com` も有効。
  → 新たな権限付与や API 有効化は不要。LB はサーバレス NEG で**サービス単位**を指すため、トラフィック分割は
  Cloud Run 側で完結し LB 変更は不要。

## 現状のデプロイ機構（調査結果）

- `infra/gcp/cloud-run.tf`: `google_cloud_run_v2_service.api`（`ingress = INTERNAL_LOAD_BALANCER`）に
  `traffic` ブロックなし → 最新リビジョンへ 100%。
- マイグレーション: `docker/api.Dockerfile` runtime CMD `alembic upgrade head && exec uvicorn ...`
  （冪等・アドバイザリロックで直列化）。DB は asyncpg で `/cloudsql/<conn>` の unix ソケット接続、
  `DATABASE_URL` は Secret Manager（`secrets.tf`）。
- CI: `.github/workflows/deploy-gcp.yml`（image build/push → Trivy → `terraform apply` → ヘルスチェック）。
- DB: `google_sql_database_instance.main` の**単一インスタンス**を共有。

## 対応（実装）

### Phase 0: マイグレーション分離 ＋ expand-contract 規約（前提・最重要）

- `docker/api.Dockerfile` runtime CMD から `alembic upgrade head &&` を除去（起動時マイグレーション廃止）。
  dev ステージ（再試行ループ）は据え置き（ローカルは単一インスタンスで on-boot が便利）。
- `infra/gcp/cloud-run.tf` に `google_cloud_run_v2_job.migrate` を追加（api SA / VPC コネクタ /
  Cloud SQL ソケットボリューム / `database-url` secret / `image = var.container_image_api` /
  `command = ["alembic","upgrade","head"]`）。
- `compose.prod.yml` に一回実行の `migrate` サービスを追加し、api を `service_completed_successfully` に依存。
- CI（`deploy-gcp.yml`）の順序変更: image push → Trivy → **`terraform apply -target=migrate Job`** →
  **`gcloud run jobs execute --wait`（expand 先行）** → Phase 1 のカナリア切替 → `terraform apply`（full）。
- **expand-contract 規約**を `CLAUDE.md`（DB セクション）に明記: 列追加は nullable/default 付き。削除・改名・
  NOT NULL 化・型変更は**単一リリースで完結させない**（追加 → 両対応 → 次リリースで縮約）。green と blue が
  同一 DB を同時利用するため、破壊的変更は blue 退役後の別リリースで contract する。

### Phase 1: 段階カナリア（gcloud 主導）

- `infra/gcp/cloud-run.tf` の api service に
  `lifecycle { ignore_changes = [template[0].containers[0].image, traffic] }` を追加
  （TF が 100% 差替・トラフィックを上書きしないよう、リビジョン/トラフィックは gcloud 主導に）。
- `infra/gcp/monitoring.tf`: 5xx ログメトリックに `resource.labels.revision_name` を加え、
  カナリア中のリビジョン別 5xx を観測可能に（切替判断・将来の自動ロールバックの下地）。
- CI（`deploy-gcp.yml`）:
  - green を無トラフィック・タグ付きでデプロイ（`gcloud run deploy ... --no-traffic --tag green
    --revision-suffix <shortsha>`）。
  - 段階シフト（`gcloud run services update-traffic ... --to-tags green=10` → LB 経由ヘルス確認 →
    `green=100`）。旧リビジョン保持で `--to-revisions <old>=100` により即ロールバック。
  - ヘルス NG 時は旧リビジョンへ戻して非ゼロ終了。
  - 注: api は `ingress=内部LB` のため green タグ URL の隔離スモークは不可 → 10% を通してからの
    LB 経由確認が現実解。

## 影響範囲

- **フロントエンド変更なし**。
- api（Cloud Run）: リビジョン/トラフィック管理を gcloud 主導へ。config（env/スケーリング/probe/secret）は
  引き続き TF 管理。
- DB（Cloud SQL 単一インスタンス）: expand-contract 規約の遵守が必須（運用ルール）。
- service ワーカー: カナリア対象外。expand マイグレーション後に通常デプロイ。旧 api と互換であることを規約で担保。
- CI/CD: デプロイ順序とカナリア手順の追加。
- TF ↔ gcloud の役割分担（config は TF、image/traffic は gcloud）。

## 受け入れ条件

- api リビジョンが起動時にマイグレーションを実行しない（ログで確認）。マイグレーションは `migrate` Job で先行適用。
- デプロイ時、green が 0% → 10% → 100% と段階的に切り替わり、各段で `GET /api/v1/health` が 200。
- 旧リビジョンが保持され、`gcloud run services update-traffic --to-revisions <old>=100` で即ロールバックできる。
- ヘルス NG のときにデプロイが失敗し、トラフィックが旧リビジョンに戻る。
- stg で検証後、prod でも同フローで動作する。

## 参照

- インフラ: `infra/gcp/cloud-run.tf`（api service / migrate Job）、`infra/gcp/monitoring.tf`、
  `infra/gcp/secrets.tf`（`database-url`）、`infra/gcp/load-balancer.tf`（サービス単位 NEG）
- デプロイ: `.github/workflows/deploy-gcp.yml`、`docker/api.Dockerfile`、`compose.prod.yml`
- マイグレーション: `backend/api/alembic.ini`、`backend/api/app/alembic/`（0001→ の線形チェーン）
- 規約: `CLAUDE.md`（DB 所有権・expand-contract）
- Phase 2（対象外）: 監視連動の自動ロールバック、破壊的変更（contract）の運用。issue 070（運用ハードニング）と関連。
