# コード負債検知パイプラインを service に追加する（重複 / dead / 複雑度 + AI 生成痕跡）

## 概要

負債レジストリ（Matrix）の `CodeDebt` 行と Overview 散布図の「コード品質軸」は、現在いずれもフロントの
モック（`frontend/src/lib/api/mock/debts.ts` の `MOCK_DEBTS`、`frontend/src/lib/mock/overview-mock.ts`）を
直接描画しているだけで、**裏側の検知・永続化が存在しない**。`client.listDebts` / `client.getDebt` は
`// TODO: GET /api/v1/orgs/${orgSlug}/debts に差し替え` のまま mock を返す（`client.ts:311` / `:317`）。

本 issue は、その **コード負債（重複 / dead / 複雑度）と AI 生成痕跡** を検知して永続化する非同期
パイプラインを **service** に新設する。018 で確立した三つ組（`(RequestSchema, ResultSchema, process)`）と
方式 B（`installation_id` のみ搬送、service が Secret Manager から token を mint）をそのまま踏襲し、
api は `stack.py` の `analyze_stack` を雛形に `POST .../detect-debts → 202 {job_id}` の enqueue に徹する。

具体的には次に絞る：

1. `shared/shared/models/` に **`code_debts`** ORM を新設（`tech_stack.py` 雛形）。Matrix の `codeDebtSchema`
   （`schemas.ts:230-249`）に対応するカラム群 + `code_debt_score` / `knowledge_coverage` / `ai_generation_prob`
   / `estimated_repay_hours` / `metrics` JSON を持つ。
2. `shared/shared/enums.py` の `JobType` に **`code_debt_detection`** を追加（命名規約は 026 で確立した
   lowercase snake_case = queue path）。
3. `shared/shared/schemas/code_debt_detection.py` に **Request / Result**（`JobRequestBase` / `JobResultBase`
   継承・`GitHubRef` で `installation_id` 方式 B）を新設。
4. `service/service/pipelines/code_debt_detection.py` の `process` を実装し、`service/service/registry.py` に
   三つ組登録（`stack_analysis.py` 雛形、`ctx.session` で upsert）。
5. 検知：`GitHubGitClient`（027 拡張）でツリー/内容/履歴を取得 → 複雑度・重複・dead の静的解析 +
   `gemini_stack_service`（Vertex AI + ADC）で AI 生成痕跡を推定。**severity 量子化しきい値（float→enum 4 段）**
   と **`derive_priority(code, 1−know)`** を本 issue で確定する。
6. api は `POST .../detect-debts → 202 {job_id}` enqueue のみ（`stack.py` 雛形）。

> 本 issue は **配信一覧 API（`GET .../debts`）と返済 PR 生成を作らない**（031 / 033 が所有）。
> ここでは「検知して `code_debts` を永続化する」までを所有する。知識負債（`reason` 系）の検知は 030。

## 背景・目的

### 現状（コード負債の検知・永続化が無い）

- フロント契約は `frontend/src/lib/api/schemas.ts:230-249` の `codeDebtSchema` が確定済み
  （doc 008 の `CodeDebt` UI 投影スキーマ）。`type`（`duplicate` / `dead` / `complexity` / `other`）・
  `severity`（`critical` / `high` / `medium` / `low`）・`status`（`open` / `in_pr` / `resolved` / `dismissed`）・
  `code_debt_score` / `knowledge_coverage` / `ai_generation_prob`（いずれも 0..1）・`archaeology_notes` /
  `code_snippet` / `estimated_repay_hours` / `related_pr` / `related_adr`（nullable）を持つ。
- これらを生む実体が DB に無く、`MOCK_DEBTS`（`mock/debts.ts:5`）が 8 件のダミーを返している。
- 非同期基盤（016/018）と解析データ基盤（026 の `analysis_run` / `repo_file`）・git 履歴クライアント
  （027 の `GitHubGitClient` 拡張）は本 issue の前提として整っている想定。本 issue はその上に
  「コード負債検知」という最初の解析パイプラインを載せる。

### 目的

1. `code_debts` 共有 ORM を新設し、Matrix `codeDebtSchema` を満たすデータを横断クエリ可能な正規化テーブルに置く。
2. `code_debt_detection` パイプラインを service に新設し、重い解析（git 取得・静的解析・Gemini）を api の
   リクエストパス外で実行する。
3. severity の float→enum 量子化しきい値と、`business_impact` 未取得フェーズの優先度近似
   `derive_priority(code, know)` を本 issue で**確定**する（doc 008 の `derivePriority` `008:294` を裏側に移植）。
4. api は `POST .../detect-debts → 202 {job_id}` の enqueue + `GET /jobs/{id}` ポーリングに徹する。

### 前提 issue（depends_on）

- **026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run`（run スコープ）/
  `repo_file`（File 同一性アンカー）共有テーブルと `JobType` 追加規約・pgvector 拡張。`code_debts` は
  `run_id`（→ `analysis_run`）/ `repo_file` を join キーとして参照する。
- **027** `docs/issue/027-backend-github-history-client-extension.md` — `GitHubGitClient` の commit 履歴・blame・
  依存抽出拡張（方式 B 維持）。AI 生成痕跡推定の `related_pr` / 自動 approve 判定や複雑度・重複解析の
  対象取得に利用する。

> 暗黙の前提は 016 / 018 の非同期基盤（`Job` / `enqueue_job` / `run_task` / 三つ組登録 / 方式 B）。
> 本 issue は新しいキュー基盤を作らず、`code_debt_detection` という解析パイプラインを既存基盤に載せる。

## データモデル

### 新規テーブル `code_debts`（shared ORM・api が Alembic 0007 で作成）

`shared/shared/models/code_debt.py` を新設する（`shared/shared/models/tech_stack.py` 雛形：`uuid4` PK・
`DateTime(timezone=True)`・JSON 列・`UniqueConstraint`、依存は `pydantic` + `sqlmodel` のみ）。
カラムは `codeDebtSchema`（`schemas.ts:230-249`）に対応させる：

| カラム | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`uuid4` PK） | `codeDebtSchema.id`（フロントは string） |
| `project_id` | `uuid.UUID`（FK 規約は 026 の `analysis_run` に合わせる） | プロジェクト単位スコープ（1 project = 1 repo） |
| `run_id` | `uuid.UUID`（FK → `analysis_run.id`） | どのスナップショットで検知したか（026） |
| `file_path` | `str`（index） | `codeDebtSchema.file_path`。`repo_file`（026）と (run_id, path) で対応 |
| `type` | `str`（enum: `duplicate` / `dead` / `complexity` / `other`） | `codeDebtSchema.type`（`schemas.ts:235`） |
| `severity` | `str`（enum: `critical` / `high` / `medium` / `low`） | float→enum 量子化（後述しきい値） |
| `status` | `str`（enum: `open` / `in_pr` / `resolved` / `dismissed`、default `open`） | `codeDebtSchema.status`（`schemas.ts:237`） |
| `detected_at` | `datetime`（`DateTime(timezone=True)`） | `codeDebtSchema.detected_at`（offset 付き iso） |
| `related_pr` | `str \| None` | `codeDebtSchema.related_pr`（nullable） |
| `related_adr` | `str \| None` | `codeDebtSchema.related_adr`（nullable） |
| `archaeology_notes` | `str` | 検知根拠の人間可読文（"循環的複雑度 24" 等。mock `debts.ts:17-18` の文体） |
| `code_snippet` | `str` | 該当コード断片（詳細ビューの file-viewer 表示用。`schemas.ts:242`） |
| `code_debt_score` | `float`（0..1） | 静的解析スコア（縦軸＝コード品質） |
| `knowledge_coverage` | `float`（0..1） | KC(file)。**本 issue では 029 未実装のため暫定値**（後述「保留」） |
| `ai_generation_prob` | `float`（0..1） | Gemini による AI 生成痕跡推定 |
| `estimated_repay_hours` | `float` | 推定返済コスト |
| `metrics` | `dict`（JSON） | 複雑度・重複・dead の生指標（循環的複雑度・重複クラスタ・到達不能行数 等） |

- `assigned_agent`（`codeDebtSchema` は `literal "code_debt"`）はテーブルに持たず、配信時（031）に固定値で
  投影する。`assigned_developers` は KC(file,dev)（029/030）に依存するため**本 issue では空配列扱い**とし、
  031 が join して埋める（重複定義を避ける。本 issue では検知のみ所有）。
- `priority`（P0–P3）は派生値であり、`code_debt_score` × `knowledge_coverage` から都度算出する方針
  （配信は 031）。検知時に保存するか算出するかは「severity 量子化・優先度近似」節を参照。

### Alembic

- api 所有の **0007**（026 の `0006` の次。連番は実装時に最新を確認し +1）で `code_debts` を作成する
  （`api/app/alembic/versions/0003_add_tech_stacks.py` / `0005_add_jobs.py` 雛形、命名規約は `base.py` の
  naming convention 踏襲）。service は DML のみでマイグレーションを持たない。
- `shared/shared/models/__init__.py`（`models/__init__.py:3-4` で現状 `Job` / `TechStack` を re-export）に
  `CodeDebt` を **import 順 app→shared** で追記する（autogenerate のため）。

## API

api は **enqueue + ポーリング**に徹する（配信一覧 `GET .../debts` は 031 が所有）。ルートは `projects.py` の
`/orgs/{slug}/projects/{project_slug}/...` 配下に揃える（`projects.py:18-`、`OrgScope` 認可・Annotated DI
param 順序厳守）。

### `POST /api/v1/orgs/{slug}/projects/{project_slug}/detect-debts`（新規・202）

- `stack.py:105-143` の `analyze_stack` を雛形にする：`InstallationIdDep` で installation_id を解決し、
  `enqueue_job(session, dispatcher, blob_client, job_type=JobType.CODE_DEBT_DETECTION, payload=..., created_by=current_user.id)`
  を呼び、`JobEnqueuedOut(job_id, status)` を `202 Accepted` で返す（`response_model = JobEnqueuedOut`、
  `app/schemas/job.py`）。
- payload は方式 B：`{owner, repo, branch, requested_by, github: {installation_id}}`（`stack.py:128-134` と同形。
  owner/repo は project の `repo_owner` / `repo_name` から解決）。
- ポーリングは既存 `GET /api/v1/jobs/{job_id}`（`jobs.py`）をそのまま流用する。`Job.result_data` に書く
  `CodeDebtDetectionResult`（検知件数サマリ等）を返す。本 issue では `jobs.py` に stack のような結果持ち上げ
  分岐を追加する必要はない（一覧の実データ配信は 031）。

> 配信スキーマ（`debtListSchema` / `debtItemSchema`、`schemas.ts:270-274`）に一致させる `GET .../debts` は
> **031 が所有**。本 issue では「検知 → `code_debts` 永続化」までで、フロント `listDebts` / `getDebt`
> （`client.ts:311` / `:317`）の差し替えは 031 と連携する。

## パイプライン・非同期

### JobType / スキーマ

- `shared/shared/enums.py` の `JobType`（`enums.py:11-16`、現 `echo` / `ping` / `stack_analysis`）に
  `CODE_DEBT_DETECTION = "code_debt_detection"` を追加する（queue path = `code-debt-detection`）。
- `shared/shared/schemas/code_debt_detection.py` を新設（`stack_analysis.py` 雛形）：
  - `CodeDebtDetectionRequest(JobRequestBase)`：`owner` / `repo` / `branch="main"` / `github: GitHubRef` /
    `requested_by` / `project_id` / `run_id`（026 の run と紐付け）。`GitHubRef`（`installation_id` + 任意
    `access_token`）は `shared/shared/schemas/stack_analysis.py:45` の既存定義を import 再利用する。
  - `CodeDebtDetectionResult(JobResultBase)`：`detected: int`（検知件数）・`by_type: dict[str, int]`・
    `by_severity: dict[str, int]` 等のサマリ。詳細行は `code_debts` テーブルに書くので result_data には
    サマリのみ載せる（018 の `agent_trace` 相当の軽量サマリ）。

### service パイプライン `code_debt_detection.py`

- `service/service/pipelines/code_debt_detection.py` に `process(request, ctx) -> CodeDebtDetectionResult`
  を実装する（`stack_analysis.py:361-389` を雛形）。`shared.worker.run_task` が `Job` ライフサイクル
  （PROCESSING → COMPLETED/FAILED・冪等）と `Job.result_data` 書き込みを所有する。`ctx.session`
  （`PipelineContext`、`context.py:18-22`）で `code_debts` を upsert する。
- トークン mint は `stack_analysis._mint_installation_token`（`stack_analysis.py:332-342`）と同型（方式 B、
  `GitHubAppService.get_installation_token`）。
- 検知フロー：
  1. `GitHubGitClient`（027 拡張）でツリー/内容/commit 履歴/PR メタを取得（`get_repository_tree` /
     `get_file_content` は既存 `github_git_client.py`、commit/PR は 027）。
  2. **複雑度**：言語別に循環的複雑度を算出（しきい値超過を `complexity`）。`metrics` に生値。
  3. **重複**：コード片の正規化比較（MVP）。pgvector による埋め込み類似（026 で拡張有効化済み）は将来。
  4. **dead**：依存グラフ（027 の依存抽出ヘルパ）で到達不能を判定（`dead`）。
  5. **AI 生成痕跡**：`gemini_stack_service`（Vertex AI + ADC、`gemini_stack_service.py`）を流用拡張し、
     コード断片 + PR メタ（自動 approve 等、027）から `ai_generation_prob`（0..1）を推定。
  6. 各検知を `code_debts` 行に upsert（`stack_analysis.save_stack` の `pg_insert(...).on_conflict_do_update`
     パターン `stack_analysis.py:214-230` を踏襲。一意制約は (run_id, file_path, type) 等を本実装で確定）。
- `service/service/registry.py`（`registry.py:15-18`）の `PIPELINES` に
  `JobType.CODE_DEBT_DETECTION.value: (CodeDebtDetectionRequest, CodeDebtDetectionResult, code_debt_detection.process)`
  を追加する。
- Vertex AI は ADC（google-api-key 不使用）。秘密は Secret Manager（方式 B）。

### severity 量子化・優先度近似（本 issue で確定）

doc 008 は「severity を float→enum に量子化（しきい値は本実装で確定。`008:180`）」「priority は
`derivePriority(code, know)` で二軸近似（`business_impact` 未取得フェーズ。`008:294-304`）」と委ねている。
本 issue で次を確定する：

- **severity 量子化**（`code_debt_score` ∈ [0,1] を 4 段へ）：`critical ≥ 0.75` / `high ≥ 0.5` /
  `medium ≥ 0.25` / `low < 0.25`。`code_debts.severity` 列に量子化済み enum を保存する。
- **優先度近似** `derive_priority(code, know)`（`know = 1 − knowledge_coverage`、doc `008:294` の
  `derivePriority` を Python へ移植）：`P0 if code≥0.6 and know≥0.6` / `P1 if 一方≥0.6` /
  `P2 if 一方≥0.3` / `else P3`。`business_impact` は未取得のため第 3 軸は省く（doc `008:304`）。
  priority は派生値のため `code_debts` には列を持たず、配信時（031）に算出する（重複定義回避）。

> しきい値は外部仕様書（§7.1）が repo 内に無いため、上記は **製品判断として本 issue で明示**する数値である
> （捏造ではなく、mock の数値帯と doc の 0..1 範囲・`derivePriority` バンドに整合させた確定値）。

### 定期スキャン

定期的なコード負債検知トリガーは Cloud Functions + Cloud Scheduler/Pub-Sub（CLAUDE.md「非同期ジョブ =
Cloud Functions（定期スキャン・Pub/Sub トリガー）」）で project を巡回 enqueue する設計だが、**その
Terraform 実装は 037 が所有**。本 issue は手動トリガー（`POST .../detect-debts`）の検知パイプラインまで。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `shared/shared/enums.py` の `JobType`（`enums.py:11-16`）に `CODE_DEBT_DETECTION = "code_debt_detection"` を追加する。
- [ ] `shared/shared/models/code_debt.py` を新設する（`shared/shared/models/tech_stack.py` 雛形：`uuid4` PK・
      `DateTime(timezone=True)`・JSON 列・`UniqueConstraint`）。上記「データモデル」のカラム群を持つ。
- [ ] `shared/shared/models/__init__.py`（`models/__init__.py:3-6`）に `CodeDebt` を import 順 app→shared で追記し `__all__` に加える。
- [ ] `shared/shared/schemas/code_debt_detection.py` を新設し `CodeDebtDetectionRequest` / `CodeDebtDetectionResult`
      を定義する（`shared/shared/schemas/stack_analysis.py:58-77` 雛形。`GitHubRef` は `stack_analysis.py:45` を再利用）。

### api（`backend/api/app/`）

- [ ] api 所有の Alembic マイグレーション（026 の `0006` の次。実装時に最新を確認）で `code_debts` を作成する
      （`api/app/alembic/versions/0003_add_tech_stacks.py` 雛形）。
- [ ] `POST /api/v1/orgs/{slug}/projects/{project_slug}/detect-debts` を追加する
      （新規 `app/api/v1/debts.py` または既存ルーターへ。`stack.py:105-143` の `analyze_stack` を雛形に
      `enqueue_job` + `JobEnqueuedOut` 202、`OrgScope` 認可、Annotated DI param 順序厳守）。
- [ ] `app/api/v1/router.py`（`router.py:9,19`）に新ルーターを `include_router` する（debts 配信は 031 で拡張）。

### service（`backend/service/service/`）

- [ ] `service/service/pipelines/code_debt_detection.py` の `process(request, ctx)` を実装する
      （`service/service/pipelines/stack_analysis.py:361-389` 雛形、`ctx.session` で `code_debts` upsert、
      トークン mint は `_mint_installation_token` `stack_analysis.py:332-342` と同型）。
- [ ] 複雑度・重複・dead の静的解析ヘルパと severity 量子化（`critical≥0.75 …`）を実装する。
- [ ] `gemini_stack_service`（`service/service/services/gemini_stack_service.py`）を流用拡張し `ai_generation_prob` を推定する（Vertex AI + ADC）。
- [ ] `GitHubGitClient`（027 拡張、`service/service/services/github_git_client.py`）で commit 履歴/PR メタ/依存を取得する。
- [ ] `service/service/registry.py`（`registry.py:15-18`）の `PIPELINES` に三つ組を追加する。

### frontend（`frontend/src/lib/api/`）

- [ ] `client.ts` に `detectDebts(orgSlug, projectSlug)` を追加する（`POST .../detect-debts → 202 {job_id}`、
      既存 `analyzeStack` / `getJob`（`client.ts`）と同じ enqueue + ポーリング規約）。一覧の実データ化
      （`listDebts` `client.ts:311` / `getDebt` `client.ts:317` の TODO 差し替え）は **031 と連携**するため
      本 issue では検知トリガーの結線のみ。
- [ ] `schemas.ts` に enqueue 応答用スキーマ（既存 `analyzeStackJobSchema` `schemas.ts:157` を流用 or 同形追加）を確認する。

### test

- [ ] api（`backend/api/tests/`）：`POST .../detect-debts` が `202` + `job_id` を返し、`Job` が `QUEUED` で
      作成され `MockTaskDispatcher.dispatch` が 1 回呼ばれること（`enqueue_job` 経由）。エージェント/解析を直接実行しないこと。
- [ ] service（`backend/service/tests/`）：`code_debt_detection.process` のパイプラインテスト
      （`GitHubGitClient` と Gemini/Vertex を**モック**）。`code_debts` が upsert され、severity 量子化と
      `derive_priority` が確定しきい値どおりに動くこと。at-least-once 再配送で二重生成されない冪等性。
- [ ] service：方式 B（service が token を mint）経路のテスト。

## 完了条件

- `POST .../detect-debts` が `202` + `job_id` を返し、api リクエストは解析完了を待たずに即座に返ること。
- service が api リクエスト外で複雑度・重複・dead 解析 + AI 生成痕跡推定を実行し、`code_debts` を Cloud SQL に
  永続化すること（`Job` は `run_task` が COMPLETED/FAILED に冪等更新、結果サマリを `result_data` に書く）。
- `code_debts` の各行が `codeDebtSchema`（`schemas.ts:230-249`）の `type` / `severity` / `status` /
  `code_debt_score` / `ai_generation_prob` 等を満たす形で保存されること（配信 `GET .../debts` は 031）。
- severity の float→enum 量子化しきい値と `derive_priority(code, know)` が本 issue の確定値どおりに実装されること。
- バックエンド：`cd backend && uv run ruff check shared/shared api/app service/service && uv run ruff format --check ...`
  / `uv run ty check ...` / `uv run --directory service pytest` / `uv run --directory api pytest` が通ること。
- フロント：`cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通ること。
- `CHANGELOG.md`（日本語）に `Added`（code_debt_detection パイプライン・`code_debts` テーブル）を追記。

## 対象外・保留

- **知識負債（`reason` 系）の検知** — `knowledge_debts`（`ai_generated` / `author_left` / `no_review`）は 030。
- **配信一覧 / 詳細 API** — `GET .../debts` / `GET .../debts/{id}`（`debtListSchema` / `debtItemSchema` 一致）と
  フロント `listDebts` / `getDebt` の mock 差し替えは 031。
- **返済 PR 生成** — `POST .../debts/{id}/repayment-pr`（`createRepaymentPr` `client.ts:331` の `ComingSoonError`
  スタブ差し替え）は 033。
- **KC(file) 本算出** — `knowledge_coverage` の正確値は 029（KC パイプライン）が所有。本 issue は 029 未実装の
  フェーズでは暫定値（例：未算出を示す 0.0 や中央値）を入れ、029 完了後に join で上書きする方針とする
  （捏造した KC を確定値として保存しない）。
- **`assigned_developers` の充填** — KC(file,dev)（029/030）依存のため本 issue では空配列。031 が join して埋める。
- **定期スキャン基盤**（Cloud Functions + Scheduler/Pub-Sub）の Terraform 実装は 037。
- **pgvector による重複検知**（埋め込み類似）は将来拡張（拡張有効化は 026 済み、本 issue は正規化比較の MVP）。

## 参考

- 関連 issue
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file` / JobType 規約 / pgvector（前提）
  - `docs/issue/027-backend-github-history-client-extension.md` — `GitHubGitClient` の履歴・blame・依存抽出拡張（前提）
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 非同期パイプライン三つ組・方式 B の雛形元
  - `docs/issue/008-matrix-debt-registry-drilldown.md` — `CodeDebt` UI 投影スキーマ・severity 量子化・`derivePriority`（`008:180,294-304`）
  - `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — 知識負債検知（責務分界）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — 配信一覧 / 詳細 API（責務分界）
- フロント契約 / mock
  - `frontend/src/lib/api/schemas.ts:230-249`（`codeDebtSchema`）/ `:270-274`（`debtListSchema` / `debtItemSchema`）
  - `frontend/src/lib/api/mock/debts.ts:5`（`MOCK_DEBTS`）— 検知出力の形・`archaeology_notes` 文体の参照
  - `frontend/src/lib/api/client.ts:311`（`listDebts` TODO）/ `:317`（`getDebt`）/ `:331`（`createRepaymentPr` スタブ）
- 既存バックエンド（雛形 / 流用）
  - `backend/api/app/api/v1/stack.py:105-143`（`analyze_stack` = 202 enqueue 雛形）/ `:146-167`（`get_stack`）
  - `backend/service/service/pipelines/stack_analysis.py:361-389`（`process`）/ `:214-230`（upsert）/ `:332-342`（方式 B mint）
  - `backend/shared/shared/schemas/stack_analysis.py:45-77`（`GitHubRef` / Request / Result 雛形）
  - `backend/shared/shared/models/tech_stack.py`（ORM 雛形）/ `backend/shared/shared/models/__init__.py:3-6`（re-export）
  - `backend/shared/shared/enums.py:11-16`（`JobType`）/ `backend/service/service/registry.py:15-18`（三つ組登録）
  - `backend/shared/shared/pipelines/context.py:18-22`（`PipelineContext`）/ `backend/service/service/services/gemini_stack_service.py`（Vertex AI + ADC）
  - `backend/api/app/api/v1/projects.py:18-`（`/orgs/{slug}/projects/{project_slug}` ルート形・`OrgScope`）/ `backend/api/app/api/v1/router.py:9,19`（ルーター登録）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — Python snake_case / 方式 B / Secret Manager / Vertex AI + ADC / Annotated DI param 順序厳守 /
    `models/__init__.py` import 順（app→shared）/ JobType 追加・router 登録 / PATCH 規約 / ゲート（ruff・ty・pytest / bun check・lint・test:unit）/ CHANGELOG（日本語）
