# 実運用ハードニング — 監視・ロールバック・可観測性・拡張性の底上げ

## 概要

ハッカソン審査基準

> **実装力** — 選定した技術や構成の納得度、拡張性や実運用への配慮など、利用を必須としたツールを
> 活用したうえで、これらがどれだけ実現できているかを総合的に評価する。

の「**拡張性 / 実運用への配慮**」を引き上げるための、独立して着手可能なハードニング項目の束。
土台（WIF・Trivy・冪等 Job・認証・テスト）は既に堅いが、**Day-2 運用の接着剤**（通知・ロールバック・
readiness・構造化ログ・滞留ジョブ回収）と**拡張性の見栄え**（ページング・IaC モジュール化）に空白がある。

本 issue は **AI エージェント中核化（[issue 069](069-agentic-analysis-with-adk-twin-agent-core.md)）とは別軸**で、
そちらが「価値の中心が AI か」を、本 issue が「実運用に耐える構成か」を担保する。各タスクは疎結合で、
別々の担当者が並行着手できるよう **現状 / 対応 / 受け入れ条件 / 参照** を明記する。

## 背景（監査で検証済みの弱点）

実コードで裏取りした、実運用・拡張性の観点でのギャップ：

| 観点 | 実態（検証済み） | 出典 |
|---|---|---|
| 滞留ジョブ回収 | `timeout_stale_jobs()` は完成しているが **本番の定期実行呼び出しが無い**（呼ぶのはテストのみ。docstring は不在の `result_poller` を参照） | `backend/api/app/services/job_orchestrator.py:68-89`、`backend/api/tests/api/v1/test_stack.py:214` |
| アラート通知 | `api_5xx` alert policy はあるが **`notification_channels` 未設定**・通知チャネルリソースも無い → 5xx を検知しても無通知 | `infra/gcp/monitoring.tf:14-34` |
| readiness | `/health` は **liveness のみ**（DB 未チェック。docstring が「readiness は別途」と明記） | `backend/api/app/api/v1/health.py:20-27` |
| 構造化ログ | plain `logging`、**相関 ID 無し** → トレース困難 | `backend/service/service/main.py`、`backend/api/app/main.py` |
| LLM 出力検証 | `json.loads` 失敗時に **`_empty_result()` の沈黙 fallback**（9 関数）。pydantic 検証なし | `backend/service/service/services/gemini_stack_service.py:150,165-171 ほか` |
| ロールバック | デプロイは `terraform apply -auto-approve` で **新リビジョン即 100% 切替**。切り戻し手段がほぼ無い | `.github/workflows/deploy-gcp.yml:171-177` |
| ページング | `list_project_debts` は filter/sort のみで **`limit`/`offset` 無し**（unbounded）。実装済みは `users` のみ | `backend/api/app/api/v1/debts.py:87-97`、`backend/api/app/api/v1/users.py:34-48` |
| LLM コスト | トークン/レイテンシ/コストの **計測なし**（ファイル数・サイズ上限はある） | `gemini_stack_service.py`（`_generate`） |
| IaC DRY | `cloud-run.tf` の `api` と `service` が `template`/`scaling`/`vpc_access`/`volumes` で **ほぼ重複** | `infra/gcp/cloud-run.tf:65,138` |

## スコープ（タスク一覧）

凡例 — 効く軸: 運=実運用への配慮 / 可=可観測性 / 拡=拡張性 ・ 工数: 小=数時間 / 中=1日前後

| # | タスク | 効く軸 | 工数 | 優先 |
|---|---|---|---|---|
| T1 | 滞留ジョブ回収を定期実行に接続 | 運 | 小 | 高 |
| T2 | アラート通知チャネルの追加 | 運 | 小 | 高 |
| T3 | readiness probe の追加 | 運 | 小 | 高 |
| T4 | 構造化ログ + 相関 ID | 運/可 | 小〜中 | 中 |
| T5 | LLM 出力の Pydantic 検証 | 運/可 | 小 | 中 |
| T6 | Cloud Run トラフィック分割でカナリア/ロールバック | 運 | 中 | 中 |
| T7 | ページネーションの共通化 | 拡 | 中 | 中 |
| T8 | LLM トークン/コスト計測 | 運/可 | 小 | 中 |
| T9 | cloud-run.tf の module 化（DRY） | 拡 | 中 | 低 |

---

### T1. 滞留ジョブ回収を定期実行に接続 〔運・小・高〕

**現状:** `timeout_stale_jobs()`（1 時間以上 `PROCESSING` の Job を `FAILED` にする）は実装・テスト済みだが、
**本番から呼ばれていない**。`job_orchestrator.py` の docstring は `result_poller._timeout_stale_jobs` を参照するが、
その poller は存在しない。→ service クラッシュ等で取り残された Job が永久に `PROCESSING` のまま残り、UI 上のラン状態が詰まる。

**対応:**
- 定期トリガを追加（推奨: Cloud Scheduler → 内部エンドポイント）。
  - 案 A: api に `POST /internal/tasks/reap-stale-jobs` を追加し OIDC で保護（既存 Cloud Tasks の OIDC audience パターンを流用）、Cloud Scheduler から 15–30 分周期で叩く。
  - 案 B: service 側に reaper パイプラインを追加し Cloud Scheduler → Cloud Tasks/HTTP で起動。
- `infra/gcp` に `google_cloud_scheduler_job` を追加（stg/prod の周期を tfvars 化）。Cloud Scheduler API 有効化を `apis.tf` に追加。

**受け入れ条件:**
- `started_at` が閾値超の `PROCESSING` Job が次サイクルで `FAILED`（`error="Job timed out"`）になる統合テスト。
- スケジューラが Terraform で定義され、エンドポイントは未認証アクセスを拒否する。

**参照:** `backend/api/app/services/job_orchestrator.py:68-89`、`backend/api/tests/api/v1/test_stack.py:214`

---

### T2. アラート通知チャネルの追加 〔運・小・高〕

**現状:** `google_monitoring_alert_policy.api_5xx` は条件のみで `notification_channels` が空。通知先リソースも無いため、
5xx 急増を検知しても誰にも通知されない。uptime check も alert policy に未接続。

**対応:**
- `google_monitoring_notification_channel`（email もしくは Slack/PagerDuty webhook）を追加し、宛先を変数化（stg/prod で別）。秘匿値は Secret Manager / tfvars 経由。
- `api_5xx` policy の `notification_channels` に紐付け。
- （任意）uptime check 失敗にも alert policy を追加。

**受け入れ条件:** `terraform plan` で alert policy に notification channel が紐づく。宛先がコード直書きでなく変数/シークレット。

**参照:** `infra/gcp/monitoring.tf:14-34, 37-57`

---

### T3. readiness probe の追加 〔運・小・高〕

**現状:** `/health` は liveness のみで DB を確認しない（docstring が明記）。Cloud Run の startup/readiness probe で依存性を見ていないため、DB 断時にも「準備完了」と判定され、トラフィックが流れうる。

**対応:**
- `GET /health/ready` を追加し、DB へ軽量クエリ（`SELECT 1`）で疎通確認（任意で GCS/Gemini 到達性。重い外部呼び出しは避ける）。失敗時 503。
- Cloud Run の `startup_probe`（必要なら `liveness_probe`）を `/health/ready` に設定。liveness は `/health` を維持。

**受け入れ条件:** DB 接続不可時に `/health/ready` が 503。Cloud Run の probe が Terraform で設定される。`/health` は従来通り 200。

**参照:** `backend/api/app/api/v1/health.py:20-27`、`infra/gcp/cloud-run.tf`（`template` 内 probe）

---

### T4. 構造化ログ + 相関 ID 〔運/可・小〜中〕

**現状:** plain `logging`（`logger.info/warning/exception`）で出力、相関 ID が無く、リクエスト/ジョブ横断のトレースが困難。

**対応:**
- `structlog` または `python-json-logger` で JSON 1 行/レコードのログに統一（Cloud Logging が構造化フィールドとして取り込む）。
- api に request-id ミドルウェア（`X-Request-ID` を受領 or 生成しレスポンスに返す）。
- Job 実行（`shared.worker.run_task`）で `job_id` を `contextvar` にバインドし、全ログに自動付与。

**受け入れ条件:** 主要ログが JSON 形式で `job_id` / `request_id` を含む。1 リクエスト/1 ジョブをキーで追える。

**参照:** `backend/api/app/main.py`、`backend/service/service/main.py`、`backend/shared/shared/worker.py`

---

### T5. LLM 出力の Pydantic 検証 〔運/可・小〕

**現状:** `gemini_stack_service.py` の各 LLM 呼び出しは `json.loads(response.text)` 後、失敗・不正 shape を `_empty_result()` で
**沈黙 fallback**（9 関数）。pydantic 検証や JSON Schema 制約が無く、モデルが想定外の形を返してもバグが握り潰される。

**対応:**
- 各応答に pydantic レスポンスモデルを定義し `model_validate` で検証。検証失敗は **warning ログ + 失敗カウンタ（メトリクス）** に記録してから fallback。
- 可能なら Gemini の structured output（`response_schema`）も併用し、出力形状を制約。

**受け入れ条件:** 不正 shape が握り潰されず観測可能（ログ/メトリクス）になる。各関数に最低 1 つの検証テスト（正常/不正）。

**参照:** `backend/service/service/services/gemini_stack_service.py:78,150,165-171,189-198, ...（全 `json.loads` 箇所）`、`backend/service/service/config.py:59-61`

---

### T6. Cloud Run トラフィック分割でカナリア/ロールバック 〔運・中〕

**現状:** `deploy-gcp.yml` は `terraform apply -auto-approve` で新リビジョンへ即 100% 切替。問題発覚時の切り戻し手段がほぼ無い。

**対応:**
- Cloud Run v2 の traffic 設定で段階移行を可能にする。最小案: 新リビジョンに tag を付与し `--no-traffic` で投入 → ヘルス/メトリクス確認 → traffic を移す。
- ロールバックは前リビジョンへ traffic を戻す 1 手順として `docs/` に明文化（runbook）。

**受け入れ条件:** デプロイで即時全切替されない構成。明確な 1 手順（またはコマンド）で直前リビジョンへロールバックできることを doc 化。

**参照:** `.github/workflows/deploy-gcp.yml:171-177`、`infra/gcp/cloud-run.tf:65-213`

---

### T7. ページネーションの共通化 〔拡・中〕

**現状:** `list_project_debts` は filter/sort のみで `limit`/`offset` が無く unbounded。kc/features 等の list も同様の可能性。実装済みは `users` のみ。データ増で OOM/レイテンシ悪化の懸念。

**対応:**
- `shared`（または api 共通 utils）に共通ページングパラメータ（`limit`/`offset` もしくは cursor）とレスポンスエンベロープ（`items` / `total` / ページ情報）を定義。
- debts / kc / features の list に適用。デフォルト上限を設定（`users` の 100/上限 500 に揃える）。

**受け入れ条件:** 対象 list が `limit`/`offset` を受け、デフォルト上限を持ち、`total` を返す。各 endpoint にページングのテスト。

**参照:** `backend/api/app/api/v1/debts.py:87-97`、`backend/api/app/api/v1/users.py:34-48`

---

### T8. LLM トークン/コスト計測 〔運/可・小〕

**現状:** ファイル数・サイズ上限はあるが、LLM 呼び出しのトークン数・レイテンシ・推定コストを記録していない。本番でのコスト暴走を検知できない。

**対応:**
- `_generate` ラッパで `usage_metadata`（prompt/candidates トークン）と所要時間を構造化ログ + メトリクスに記録。
- ラン単位の合計（`Job.result_data` か専用集計）を残し、閾値超で warning。

**受け入れ条件:** 各 LLM 呼び出しの in/out トークンとレイテンシがログに出る。ラン単位の合計トークン/概算コストが追える。

**参照:** `backend/service/service/services/gemini_stack_service.py`（`_generate` と各呼び出し）、`backend/service/service/config.py`

---

### T9. cloud-run.tf の module 化（DRY） 〔拡・低〕

**現状:** `cloud-run.tf` の `api`（:65）と `service`（:138）が `template`/`scaling`/`vpc_access`/`volumes`/env でほぼ重複。変更時に二重メンテが必要。

**対応:**
- `infra/gcp/modules/cloud_run_service/` を新設し、api/service を module 呼び出しに置換。差分（CPU/memory/min-max instances/env/ingress/deletion protection）を変数化。

**受け入れ条件:** module 化後の `terraform plan` が現行構成と等価（実質 no-op、リソース置換が出ない形）であることを確認。

**参照:** `infra/gcp/cloud-run.tf:65-213`

---

## 非対象（このissueに含めない）

- **AI エージェント中核化** — [issue 069](069-agentic-analysis-with-adk-twin-agent-core.md) で扱う（Twin Agent / ADK の自律化）。本 issue は実運用・拡張性のみ。
- **eval / 回帰テスト基盤、マルチリージョン/DR、シークレットローテーション** — 価値はあるが今回のスコープ外。必要なら別 issue として起票する。

## 連動 issue

- **[069](069-agentic-analysis-with-adk-twin-agent-core.md)** — AI エージェント中核化（別軸の審査基準）。
- **016 / 018 / 042** — Cloud Tasks + `Job` ライフサイクル + `run_task`（T1・T4 の土台）。
- **037 / 064** — 解析ラン・コックピットと「解析に生成を集約」（T1 の滞留ジョブが UI 体験に直結）。
