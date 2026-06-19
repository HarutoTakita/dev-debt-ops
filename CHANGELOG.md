# 変更履歴

すべての注目すべき変更はこのファイルに記録されます。

フォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に基づいています。

## [Unreleased]

### Added

- 解析データ基盤（issue-026）: 全解析ドメイン（028 以降）が共有する `analysis_run`（リポジトリスナップショット軸）/ `repo_file`（File 同一性アンカー）共有 ORM を `shared.models` に新設、Alembic `0006` でテーブル作成 + `CREATE EXTENSION vector`（pgvector 有効化のみ、vector 列は将来）、`JobType` 命名規約（lowercase snake_case → task path）の正式化、File 同一性・dev 識別子・run スコープ・pgvector 方針の ADR（`docs/adr/0001-analysis-data-model-and-identity.md`）。配信 API・解析ロジックは含まず土台のみ。
- 二軸負債の視覚言語統一（issue-021）: 軸凡例コンポーネント（`axis-legend`、Overview マトリクスタイトル横と Galaxy KC 表示隣の info アイコンから「コード負債（amber）/ 知識被覆 KC（teal）」を提示）、`--color-warning` トークン（P1 / in_pr / in_progress を `--color-debt-code` 軸色から分離）、共通 KC フォーマッタ（`$lib/format/kc.ts` の `formatKc` / `formatKcPct`）、wormhole の from→to 方向矢印・ホバーハイライト、アバターの緑/破線インラインキー（`developer-key`）を追加。
- スタック解析の非同期パイプライン（issue-018）: ADK スタック解析を api 同期実行から service の非同期ジョブへ移設。
  - shared: `stack_analysis` の request/result スキーマ（`StackAnalysisRequest` / `StackAnalysisResult` / `TechItem` / `TechCategories` / `GitHubRef`）を追加、`TechStack` ORM モデルを `shared.models` へ昇格（api・service 双方が参照）、`PipelineContext` に `session` を追加（パイプラインが同一 DB セッションで永続化）。
  - service: `stack_analysis` パイプライン（ADK Runner + Vertex AI 分類 + GitHub クライアントを移設）と `services/`（`github_app` / `github_git_client` / `gemini_stack_service`）、`POST /tasks/stack_analysis` への登録。GitHub トークンは**方式 B**（service が Secret Manager の App 秘密鍵から installation token を都度 mint。キュー/GCS に平文の秘密を残さない）。
  - api: `GET /jobs/{id}` が stack-analysis ジョブの `agent_trace`（`result_data` 由来）と完了時 `tech_stack`（永続化済み `TechStack`）を返す。
  - frontend: enqueue + `GET /jobs/{id}` ポーリングのストア（`stack-analysis-store`）と進捗 UI、`agent_trace` を人間可読ステップへ写像するヘルパ、進捗文言（Paraglide ja/en）。
- GCP 版 Terraform（issue-017）: `infra/gcp/`（アプリスタック）と `infra/bootstrap/gcp/`（CI 用 WIF + tfstate）を新設。
  - `infra/gcp`: Cloud Run 2 サービス（api=internal-LB / service=internal-only、両者 Cloud SQL 接続 + Secret Manager 参照、env を 016 の `Settings` 名と 1:1）、Cloud Tasks キュー（rate/retry）+ tasks_invoker SA への `roles/run.invoker`、Cloud SQL PG17（prod=private IP / stg=public）、Artifact Registry、Secret Manager（`google-api-key` なし＝Vertex AI + ADC）、GCS payload バケット、VPC + Serverless VPC connector、外部 HTTPS LB + Cloud Armor（Traefik 等価のレート制限）、監視（log-based metric / uptime / alert）。
  - `infra/bootstrap/gcp`: WIF pool/provider（GitHub OIDC、environment ピン留め）+ deploy SA + concern 別 project ロール（`iam.serviceAccountUser` actAs 含む）、tfstate バケット（versioning/UBLA、鶏卵対処の注記）。tfstate prefix は `gcp/` と `gcp/bootstrap/` で分離。
  - オンライン経路に Pub/Sub リソースは一切無し（result は service が Cloud SQL 直書き）。定期スキャン用 Cloud Functions/Scheduler も本 issue では作らない。azure/aws の命名・env 分離・WIF 規約に整合。
- 非同期タスク基盤（issue-016）: api→service の Cloud Tasks ディスパッチ + Job ライフサイクルを実装。
  - shared: `Job` モデルを軽量化（enum は String 永続化）、`TaskDispatcher` / `BlobClient` Protocol、`echo` / `ping` パイプライン + レジストリ + `run_task`（冪等な DB 直書き）、camelCase 共通スキーマ、`MockBlobClient` / `parse_gcs_url`。
  - api: `CloudTasksDispatcher`（OIDC 付き）/ `MockTaskDispatcher`、`GcsBlobClient`、`enqueue_job`（GCS スピルオーバー）、`timeout_stale_jobs`、in-process mock-worker（lifespan 起動）、`GET /api/v1/jobs/{id}`、`jobs` テーブルのマイグレーション（0005）。
  - service: `POST /tasks/{pipeline}`（Cloud Tasks HTTP ターゲット）— OIDC 検証 / `$requestRef` 解決 / 冪等処理 / Cloud SQL への結果直書き（2xx ack・5xx リトライ）。
  - 結果通知は Pub/Sub を使わず service が Cloud SQL に直書きし、フロントは `GET /jobs/{id}` をポーリングする。ローカルは GCP 不要（全 mock）で end-to-end が回る。
- プロジェクト機能（issue-014）: Org 配下に第一級の Project（1 プロジェクト = 1 git リポジトリ）を導入。
  - バックエンド: `projects` テーブル + マイグレーション（org 内 slug 一意・1 リポジトリ 1 プロジェクトの部分ユニーク制約）、`/api/v1/orgs/{slug}/projects` の CRUD API、リポジトリアクセスの GitHub App 検証。
  - フロントエンド: サイドバー上部のプロジェクトスイッチャー（検索 + 最近開いた順）、プロジェクト作成フロー（RepoPicker 再利用）、プロジェクト設定（リネーム / 既定ブランチ / 削除）、Org ホーム（プロジェクト一覧）。

### Changed

- 二軸負債の KC 表記とカラー言語を統一（issue-021）: KC を表示する全箇所（`kc-gauge` / `debt-meta-panel` / `star-node` / `star-system` / `mastery-list` / `kc-meter` / 散布図ツールチップ / `developer-avatar`）を共通 `formatKc` / `formatKcPct` 経由に揃え（生 `toFixed(2)` を排除）、Galaxy の星・`masteryDot` を `--color-debt-knowledge` 由来の teal 明度ランプに統一（`cyan-300` / `teal-400` / 素の `red-500` を撤去、`black_hole` は `destructive` に）。散布図ツールチップと優先度バッジ title の生日本語を Paraglide 化。象限ラベル 4 つのコントラストを改善。
- `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack` を非同期化（issue-018）: 同期実行（`200 TechStackOut`）から **`202 {job_id}`** + Cloud Tasks enqueue へ変更。重いエージェント実行は service コンテナへ移り、api ワーカーを塞がない。フロントは同期レスポンスから enqueue + ポーリングへ切り替え。`GET .../stack`（永続化済み `TechStack` の読み出し）はインターフェース不変。api から `google-adk` / `google-genai` 依存と ADK エージェント実装を削除。
- 機能メニュー（Galaxy / Matrix / Quizzes / Agents / Learning / Repos）を `/[org]/[project]/...` 配下へ再スコープし、プロジェクト単位に切り替わるようにした。パンくずを Org > Project > 機能に拡張。
