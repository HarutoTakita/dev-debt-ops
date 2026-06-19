# Twin Agent 自律ループのオーケストレーションとナラティブ活動永続化 API を実装する

## 概要

`[org]/agents`（Twin Agent 活動ビュー、issue 011）は現在 **完全にモック駆動** である。
人格・活動ログ・パイプラインは `frontend/src/lib/mocks/agent-activity.ts` の
`MOCK_PROFILES` / `MOCK_ACTIVITIES` / `MOCK_PIPELINES` を
`frontend/src/lib/stores/agent-store.svelte.ts:16` `loadMock()` が直接読み込み、
`retry()`（`agent-store.svelte.ts:31`）/ `tick()`（同 :40）はクライアント上のステータス
遷移シミュレーションのみで API を一切呼ばない。`client.ts` に agent 専用関数は存在しない。

本 issue は、この活動ビューの**裏側**を実装する。すなわち「検知 → 分析 → 計画 → 返済 → 検証」の
5 ステージ自律ループを束ねる **オーケストレーション層** を service の非同期パイプライン
（issue 016 / 018 のパターン）として新設し、その実行過程を **一人称ナラティブ + 考古学的根拠** として
永続化して、`schemas.ts:381-456` の Zod 契約（`AgentActivity` / `AgentPipeline` / `AgentProfile`）と
同形で配信する api を立てる。

重要な線引き: 個別の検知・KC 算出・採点・PR 生成ロジックは **本 issue では実装しない**。それらは
issue 028（コード負債検知）/ 029（KC 算出）/ 030（知識負債検知）/ 033（返済 PR 生成）/ 034（クイズ
生成・採点）が所有する。本 issue は **それらの結果を束ね、Gemini で一人称 `message` + `evidence` を
生成し、ステージ/ノードのライブステータスを刻んで永続化する「束ね層」** に徹する（既存パイプラインを
sub-enqueue するか直接呼ぶかの線引きは ADR 化する。後述）。

> ライブ更新は MVP では **ポーリング**（既存 `GET /api/v1/jobs/{id}` 併用）とし、SSE/WebSocket は
> 対象外とする（issue 011 のフロント `tick()` 擬似更新を、`getPipeline` 再取得に置き換える）。

## 背景・目的

### 現状（フロントのみ・モック駆動）

- `frontend/src/lib/api/schemas.ts:381-456` に Twin Agent の契約が確定済み（全 snake_case）:
  `agentKindSchema`（:381, `["code_debt","knowledge_debt"]`）/ `agentProfileSchema`（:383,
  `kind/name/role/accent/tagline`）/ `agentStatusSchema`（:392,
  `["scanning","analyzing","creating_pr","running_quiz","succeeded","failed","pending"]`）/
  `narrativeEvidenceSchema`（:403, `type∈["first_commit","ai_generated","adr_reference","pr_review"]`,
  `label`, `detail` nullable, `href` nullable）/ `narrativeStepSchema`（:411,
  `id/status/message/evidence[]/created_at`）/ `agentActivitySchema`（:419,
  `id/kind/headline/steps[]/pipeline_id/created_at`）/ `pipelineNodeSchema`（:429,
  `id/label/status/retryable`）/ `pipelineStageSchema`（:436,
  `key∈["detect","analyze","plan","repay","verify"]/label/nodes[]`）/ `agentPipelineSchema`（:442,
  `id/kind/stages[]`）。型は `z.infer` で :448-456 にエクスポート済み。
- 配信は完全にモック: `agent-store.svelte.ts:16` `loadMock()` が `MOCK_PROFILES`（人格 2 件）/
  `MOCK_ACTIVITIES`（`act-code-1` / `act-know-1`、各 4 ステップ）/ `MOCK_PIPELINES`（`pipe-code-1` /
  `pipe-know-1`、各 5 ステージ）を読む。
- `agent-activity.ts` のモックは `pipeline_id` で activity → pipeline を参照し（`act-code-1` →
  `pipe-code-1`）、`evidence.href` に **クロスドメインリンク**（`agent-activity.ts:112` の
  `"/matrix/debt-002"` = Matrix への逆リンク）を持つ。`failed` ノードのみ `retryable: true`
  （`agent-activity.ts:142`）。
- issue 011 は「バックエンド実装（実エージェント連携）はまだ行わない」と明言（011:15, 114, 137）。
  実バックエンドの API パス・トリガー方式は 011 に定義が無く、**本 issue が新規に設計判断として明示する**。

### 目的

1. 5 ステージ自律ループ（検知 → 分析 → 計画 → 返済 → 検証）を束ねる service パイプライン
   （`code_debt_loop` / `knowledge_debt_loop`）を新設し、api リクエスト外で実行する。
2. 実行過程を `agent_pipeline` / `pipeline_node` / `agent_activity` / `narrative_step` /
   `narrative_evidence` テーブルへ逐次永続化する（partial 状態をポーリングで配信できる形）。
3. api を「ループ起動の enqueue（202）+ 活動/パイプラインの集計配信 + 失敗ノード再実行」に薄くする。
4. フロント `client.ts` に `listActivities` / `getActivity` / `getPipeline`（および profiles 取得）を新設し、
   `agent-store.svelte.ts` の `loadMock` / `tick` / `retry` を実 API 化する。

### 前提 issue（depends_on）

本 issue は **検知・算出・返済・採点の各パイプラインが既に存在すること** を束ねる層なので、以下に依存する。

- **issue 028** `docs/issue/028-backend-code-debt-detection-pipeline.md` — `code_debts` テーブルと
  `JobType.CODE_DEBT_DETECTION`。Code Debt ループの「検知 → 分析」が束ねる結果（type / severity /
  archaeology_notes / ai_generation_prob 等）の出所。
- **issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc` / `dependency` と
  `JobType.KC_ANALYSIS`。Knowledge Debt ループの「検知（KC 算出）」の出所。
- **issue 030** `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — `knowledge_debts` /
  `assigned_developers` と `JobType.KNOWLEDGE_DEBT_DETECTION`。Knowledge ループの「検知 → 分析」の出所。
- **issue 033** `docs/issue/033-backend-repayment-pr-generation-pipeline.md` — 返済 PR 生成パイプラインと
  `JobType.REPAYMENT_PR_GENERATION`。Code ループの「返済」ステージが起動する。
- **issue 034** `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — クイズ生成 /
  `JobType.QUIZ_GENERATION`。Knowledge ループの「返済」ステージが起動する。

> 間接前提: issue 016（Cloud Tasks + `Job` + GCS スピル + mock-worker）/ 018（最初の実パイプライン
> `stack_analysis` の移設パターン）。本 issue はこの基盤に新パイプラインを 2 本載せるだけで、キュー基盤は作らない。

### 独自性（他 issue との差分）

028-034 は **個別ドメインの検知/算出/生成** を所有する。本 issue はそれらを**横断して束ね**、
(a) ステージ進行の状態機械（5 ステージ × ノード）を `agent_pipeline` として永続化、
(b) 各ステップの **一人称ナラティブ** と **考古学的根拠**（first_commit / ai_generated / adr_reference /
pr_review）を Gemini で生成、(c) `evidence.href` に Matrix 等への **クロスドメインリンク** を埋める、
という「物語化 + 状態可視化」が固有の責務である。

## データモデル

すべて **shared ORM**（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）に新設し、
api が Alembic マイグレーションでテーブルを作成する（service は薄い `service/service/db.py` の
セッションで DML するのみ。issue 018 の所有権規約）。雛形は `shared/shared/models/tech_stack.py`
（`uuid4` PK・`DateTime(timezone=True)`・`UniqueConstraint`・`JSON` 列）。
`shared/shared/models/__init__.py:3-6` の import 順（app→shared は api 側の `models/__init__`、
shared 側はここ）に新モデルを追記し re-export する。

> パイプラインの `stages` / `nodes` は **JSON 畳み込みも、正規化（`pipeline_stage` / `pipeline_node`）も
> 可**。MVP は **`agent_pipeline.stages` を JSON 列に畳む**（`agentPipelineSchema` がネスト構造のため配信が単純）。
> 失敗ノードの再実行をノード単位で追跡する必要が出たら正規化に切り替える（後述の retry 設計参照）。

### `agent_pipeline`（新規・shared）

| カラム | 型 | 備考 |
|---|---|---|
| `id` | `uuid` PK | `uuid4` |
| `project_id` | `uuid` | プロジェクト（FK は張らず index。Job 同様 nullable 可） |
| `kind` | `str` | `code_debt` / `knowledge_debt`（`agentKindSchema:381`） |
| `status` | `str` | パイプライン全体の状態（`agentStatusSchema:392` 準拠）。MVP は派生でも可 |
| `stages` | `JSON` | `pipelineStageSchema:436` の配列（`key/label/nodes[]`、各 node に `id/label/status/retryable`） |
| `job_id` | `uuid` | このループを実行している `jobs.id`（ポーリング用） |
| `created_at` / `updated_at` | `DateTime(tz=True)` | |

`stages` の JSON は `schemas.ts` の `pipelineStageSchema` / `pipelineNodeSchema` 形をそのまま保持する
（5 ステージ固定: detect / analyze / plan / repay / verify）。

### `agent_activity`（新規・shared）

| カラム | 型 | 備考 |
|---|---|---|
| `id` | `uuid` PK | |
| `project_id` | `uuid` | index |
| `kind` | `str` | `code_debt` / `knowledge_debt` |
| `headline` | `str` | 物語の見出し（`agentActivitySchema:419`） |
| `pipeline_id` | `uuid` | FK → `agent_pipeline.id`（`agentActivitySchema.pipeline_id`） |
| `created_at` | `DateTime(tz=True)` | |

`steps` は `narrative_step` として正規化（partial 配信のため逐次 append したい）。

### `narrative_step`（新規・shared）

| カラム | 型 | 備考 |
|---|---|---|
| `id` | `uuid` PK | |
| `activity_id` | `uuid` | FK → `agent_activity.id` |
| `order` | `int` | 表示順（昇順。`narrativeStepSchema` は配列順だが DB は明示順序列を持つ） |
| `status` | `str` | `agentStatusSchema:392` |
| `message` | `str` | 一人称テキスト（Gemini 生成） |
| `created_at` | `DateTime(tz=True)` | |

### `narrative_evidence`（新規・shared）

| カラム | 型 | 備考 |
|---|---|---|
| `id` | `uuid` PK | |
| `step_id` | `uuid` | FK → `narrative_step.id` |
| `type` | `str` | `["first_commit","ai_generated","adr_reference","pr_review"]`（`narrativeEvidenceSchema:404`） |
| `label` | `str` | |
| `detail` | `str` nullable | |
| `href` | `str` nullable | クロスドメインリンク（例 `/matrix/{debt_id}`）。後述の検証規約を適用 |

> **人格（`agentProfileSchema:383`）は静的配信**とし、テーブルは作らない。`MOCK_PROFILES`
> （`agent-activity.ts:6-21`）相当の 2 件をサーバ側定数（api の constants / pydantic モデル）として持つ。

### Alembic

- api が `backend/api/app/alembic/versions/00NN_add_agent_loop.py` を新設して上記 5 テーブルを作成する
  （雛形 `0005_add_jobs.py:20-`、naming convention は `base.py` の convention 踏襲）。
  **連番は 028-035 が 0006 以降を順次消費する想定のため、実装時に `alembic/versions/` の最新番号 +1 を採番する**
  （現状コミット済みは `0001`〜`0005`）。
- 028（`code_debts`）/ 029（`file_kc`）/ 030（`knowledge_debts`）/ 034（`quiz_session` 等）のテーブルは
  **本 issue では作らない**。`evidence.href` / 束ねる検知結果はそれらを参照する（FK は張らず、`debt_id` 等を
  文字列/uuid で保持して href を組み立てる）。

## API

すべて `/api/v1/` 配下。ルートは projects 同様 `/orgs/{slug}/projects/{project_slug}/...`
（`projects.py:18-` の `/orgs/{slug}/projects/{project_slug}`）に揃え、`OrgScope`
（`deps.py:64`）で org メンバー認可を強制する。レスポンスは **snake_case 配信厳守**
（`schemas.ts` が snake_case 維持のため、`stack.py:36-65` の `TechStackOut` パターン = 素の `BaseModel`。
`shared` の `SharedBaseModel`（camelCase by_alias）は使わない）。`router.py:8-20` に新ルーターを `include_router` する。
**Annotated DI param 順序厳守**（`deps.py` の依存を編集する際は宣言順を変えない）。

| メソッド・パス | レスポンス | 一致させる Zod | 備考 |
|---|---|---|---|
| `POST .../agents/{kind}/run` | `202 JobEnqueuedOut`（`job_id`/`status`） | `analyzeStackJobSchema` 同型（client では新規 `runAgentLoop`） | `kind∈{code_debt,knowledge_debt}`。`code_debt_loop` / `knowledge_debt_loop` を enqueue |
| `GET .../agents/activities?kind=` | `AgentActivity[]` | `agentActivitySchema:419`（配列） | `kind` で絞り込み（`visibleActivities` 相当, `agent-store.svelte.ts:13`） |
| `GET .../agents/activities/{id}` | `AgentActivity` | `agentActivitySchema:419`（`steps`/`evidence` 入り） | |
| `GET .../agents/pipelines/{id}` | `AgentPipeline` | `agentPipelineSchema:442` | ライブステータス。`GET /jobs/{id}` 併用でポーリング |
| `POST .../agents/pipelines/{id}/nodes/{node_id}/retry` | `202 JobEnqueuedOut` | — | 失敗ノード再実行（新 Job enqueue）。CLAUDE.md「更新は PATCH」に倣い冪等・部分更新セマンティクス |
| `GET /api/v1/agents/profiles` | `AgentProfile[]` | `agentProfileSchema:383`（配列） | 静的人格配信（org 非依存。プロジェクトスコープ外でよい） |

### enqueue（`POST .../agents/{kind}/run`）

`stack.py:105-143` `analyze_stack` を雛形にコピーし、`InstallationIdDep`
（`github.py` の installation_id 解決、方式 B）+ `CurrentUser` + `SessionDep` +
`get_task_dispatcher` / `get_blob_client` を取り、`enqueue_job(session, dispatcher, blob_client,
job_type=JobType.CODE_DEBT_LOOP | KNOWLEDGE_DEBT_LOOP, payload=..., created_by=current_user.id)`
（`job_orchestrator.py:enqueue_job`）を呼んで `JobEnqueuedOut(job_id, status)` を `202` で返す。
payload には `project_id` / `owner` / `repo` / `branch` / `requested_by`（= `current_user.id`）/
`github.installation_id`（方式 B）を載せる（`stack.py:128-134` 準拠）。

### retry（`POST .../agents/pipelines/{id}/nodes/{node_id}/retry`）

`agent_pipeline.stages` JSON から該当 `node_id` を引き、`retryable == true`（= `status == "failed"`）の
ノードのみ再実行可能。失敗ステージ（例 `repay` の「返済 PR 作成」）に対応する **新 Job を enqueue** し
（MVP は単純再実行 = ステージ相当パイプラインの再 enqueue。`agent-store.svelte.ts:31` `retry()` の
「`analyzing` に戻す」挙動をサーバ側で実現）、ノード status を `analyzing` 等へ更新する。
ノード未存在 / `retryable == false` は 404 / 409。

### ポーリング配信

`GET .../agents/pipelines/{id}` は `agent_pipeline` 行を読んで `agentPipelineSchema` 形で返す。
`jobs.py:57-77` `get_job` のように、必要なら `Job.result_data` / 関連テーブルから派生状態を持ち上げてもよいが、
本 issue は **ループ専用テーブルへ逐次永続化** するため、pipelines/activities エンドポイントは
それらを読むだけで partial 状態を返せる。`GET /jobs/{id}`（`jobs.py`）は起動 Job のポーリングに併用する。

## パイプライン・非同期

### JobType 追加（shared）

`shared/shared/enums.py:11` `JobType`（現 `ECHO`/`PING`/`STACK_ANALYSIS`、`enums.py:14-16`）に追加
（lowercase snake_case = queue / task path 名。`enums.py:1-6` のドキュメント規約）:

```python
CODE_DEBT_LOOP = "code_debt_loop"            # Code Debt Agent 自律ループ（issue 036）
KNOWLEDGE_DEBT_LOOP = "knowledge_debt_loop"  # Knowledge Debt Agent 自律ループ（issue 036）
```

### request / result スキーマ（shared）

`shared/shared/schemas/agent_loop.py` を新設。`stack_analysis.py:58-77` を雛形に
`JobRequestBase` / `JobResultBase`（`shared/shared/schemas/job.py`）を継承し、`GitHubRef`
（`stack_analysis.py:45-55`、方式 B）を再利用する。

- `AgentLoopRequest`: `project_id` / `owner` / `repo` / `branch="main"` / `github: GitHubRef` /
  `kind: Literal["code_debt","knowledge_debt"]` / `requested_by`。
- `AgentLoopResult`: 束ねの要約（生成した `activity_id` / `pipeline_id` / 各ステージの終了 status）。
  実体（activity / step / evidence / pipeline 行）は process が DB に直接 upsert するため、`result_data`
  には ID と要約のみ書く（`jobs.py:74` の `agentTrace` 持ち上げパターンに倣い、必要なら trace を残す）。

### process（service）

`service/service/pipelines/agent_loop.py` を新設。`stack_analysis.py:process(request, ctx)`
（`PipelineContext`: `ctx.session`（DML）/ `ctx.blob`）を雛形に、`shared.worker.run_task`
（冪等・Job ライフサイクル・`$requestRef` 解決を吸収。`worker.py:32`）が呼ぶ `process` を書く。
ステージ進行ごとに `agent_pipeline.stages` を更新し、`agent_activity` / `narrative_step` /
`narrative_evidence` を逐次 upsert する（partial 配信のため、各ステージ完了時に commit）。

ステージ別の中身（**束ね方の線引きは ADR 化**。下記参照）:

| ステージ key | Code Debt ループ | Knowledge Debt ループ | 束ねる出所 |
|---|---|---|---|
| `detect` | コード負債検知結果を読む | KC 算出 + 知識負債検知結果を読む | 028 `code_debts` / 029 `file_kc` / 030 `knowledge_debts` |
| `analyze` | 考古学: 初出コミット・AI 生成痕跡・ADR 突合・PR レビュー | 著者離脱・形式レビュー・AI 生成 | 027 git 履歴 / 028・030 の `archaeology_notes` / `ai_generation_prob` |
| `plan` | 返済 PR の影響範囲・分割計画 | 学習プラン / クイズ計画 | 033（PR）/ 034・035（学習） |
| `repay` | 返済 PR 生成を起動 | クイズ生成を起動 | 033 `REPAYMENT_PR_GENERATION` / 034 `QUIZ_GENERATION` |
| `verify` | CI 自己確認（MVP は status 反映のみ） | 再クイズ判定 | 後続 |

各ステージで **Gemini（Vertex AI + ADC、`gemini_stack_service.py` パターン、`stack_analysis.py:_vertex_model_name`）**
を使い、検知結果を入力に **一人称 `message`**（`agent-activity.ts:34` 等の例文トーン）と **`evidence`**
（`type` / `label` / `detail` / `href`）を生成して `narrative_step` / `narrative_evidence` に書く。
git 履歴・blame・PR メタは GitHubGitClient（027 拡張）/ GitHubAppService（方式 B）で取得する。

#### sub-enqueue か直接呼ぶか（ADR 化）

ループの `repay` ステージは「返済 PR 生成（033）」「クイズ生成（034）」を起動する。これを
**(a) 既存パイプラインを sub-enqueue**（新 Job を Cloud Tasks に投げ、ループ Job は完了 / pending を記録）か、
**(b) ループ process 内で当該 pipeline の `process` を直接 import 呼び出し** するかは、再試行境界・
冪等性・実行時間（Cloud Run タイムアウト）に影響する設計判断であり、**`docs/adr/` に ADR として記す**
（推奨は MVP では「検知系（028/029/030）はループ内で結果を読むだけ / 生成系（033/034）は sub-enqueue」。
重い生成を別 Job に逃がしループ Job を短く保つ）。

### registry 登録（service）

`service/service/registry.py:15-18` の `PIPELINES` に三つ組を追加する（`stack_analysis` の隣）:

```python
JobType.CODE_DEBT_LOOP.value: (AgentLoopRequest, AgentLoopResult, agent_loop.process),
JobType.KNOWLEDGE_DEBT_LOOP.value: (AgentLoopRequest, AgentLoopResult, agent_loop.process),
```

（`kind` は request で分岐するため process は共通でよい。）

### 定期スキャン

自律ループの定期トリガー（検知の起点を定期化）は **Cloud Functions + Cloud Scheduler/Pub-Sub**
（CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub トリガー）」）で、project を巡回して
`POST .../agents/{kind}/run` 相当を enqueue する。**本 issue では実装せず**、Terraform 追加は issue 037
（定期スキャン基盤）に委ねる。MVP は手動トリガー（`POST .../agents/{kind}/run`）のみ。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `shared/shared/enums.py:14-16`（`STACK_ANALYSIS` の隣）に `CODE_DEBT_LOOP = "code_debt_loop"` /
      `KNOWLEDGE_DEBT_LOOP = "knowledge_debt_loop"` を追加。
- [ ] `shared/shared/models/agent_loop.py`（または分割）に `AgentPipeline` / `AgentActivity` /
      `NarrativeStep` / `NarrativeEvidence` ORM を新設（雛形 `shared/shared/models/tech_stack.py:19-44`、
      `uuid4` PK・`DateTime(timezone=True)`・`JSON` 列）。
- [ ] `shared/shared/models/__init__.py:3-6` に新モデルを import 追記し `__all__` へ追加（re-export 規約）。
- [ ] `shared/shared/schemas/agent_loop.py` に `AgentLoopRequest` / `AgentLoopResult` を新設
      （雛形 `shared/shared/schemas/stack_analysis.py:58-77`、`GitHubRef` 再利用、`JobRequestBase`/`JobResultBase` 継承）。

### api（`backend/api/app/`）

- [ ] `backend/api/app/alembic/versions/00NN_add_agent_loop.py`（`alembic/versions/` の最新 +1）で
      `agent_pipeline` / `agent_activity` / `narrative_step` / `narrative_evidence` を作成
      （雛形 `0005_add_jobs.py:20-`）。
- [ ] `backend/api/app/api/v1/agents.py` を新設し、`POST .../agents/{kind}/run`（202 enqueue。
      雛形 `stack.py:105-143`）/ `GET .../agents/activities` / `GET .../agents/activities/{id}` /
      `GET .../agents/pipelines/{id}` / `POST .../agents/pipelines/{id}/nodes/{node_id}/retry` /
      `GET /api/v1/agents/profiles` を実装（snake_case 配信 = 素の `BaseModel`、`stack.py:36-65` パターン）。
- [ ] `OrgScope`（`deps.py:64`）で org メンバー認可。retry は失敗ノードのみ許可（404/409）。
- [ ] 人格 2 件（`agent-activity.ts:6-21` 相当）をサーバ側定数として `profiles` で配信。
- [ ] `backend/api/app/api/v1/router.py:8-20` に `agents_router` を import & `include_router`。

### service（`backend/service/service/`）

- [ ] `service/service/pipelines/agent_loop.py` に `process(request, ctx)` を新設（雛形
      `service/service/pipelines/stack_analysis.py`）。ステージごとに検知結果（028/029/030）を読み、
      Gemini で一人称 `message` + `evidence` を生成し、`agent_pipeline` / `agent_activity` /
      `narrative_step` / `narrative_evidence` を `ctx.session` で逐次 upsert。
- [ ] `repay` ステージで返済 PR 生成（033）/ クイズ生成（034）を sub-enqueue（ADR の線引きに従う）。
- [ ] git 履歴・PR メタは GitHubGitClient（027 拡張）/ GitHubAppService（`github_app.py`、方式 B）で取得。
      Gemini は `gemini_stack_service.py`（Vertex AI + ADC）パターンを流用。
- [ ] `service/service/registry.py:15-18` の `PIPELINES` に `CODE_DEBT_LOOP` / `KNOWLEDGE_DEBT_LOOP` の
      三つ組を登録。

### frontend（`frontend/src/`）

- [ ] `frontend/src/lib/api/client.ts` に `listActivities(orgSlug, projectSlug, kind)` /
      `getActivity(orgSlug, projectSlug, id)` / `getPipeline(orgSlug, projectSlug, id)` /
      `getAgentProfiles()` / `runAgentLoop(...)` / `retryAgentNode(...)` を新設
      （`apiFetch` + `agentActivitySchema` / `agentPipelineSchema` / `agentProfileSchema` で parse。
      既存 `analyzeStack`（`client.ts:257`）/ `getJob`（:265）パターン）。
- [ ] `frontend/src/lib/stores/agent-store.svelte.ts` の `loadMock()`（:16）を実 API
      （`getAgentProfiles` + `listActivities` + 各 `getPipeline`）に差し替え。
- [ ] `tick()`（:40）を `getPipeline` 再取得ポーリングに、`retry()`（:31）を `retryAgentNode` 呼び出し →
      再取得に置き換え（`agent-status-icon` 等 UI は不変）。
- [ ] `frontend/src/lib/mocks/agent-activity.ts` は撤去せず、必要なら開発用フォールバックに残置（任意）。

### infra

- [ ] 定期スキャン（Cloud Functions/Scheduler/Pub-Sub）は **本 issue 対象外**（issue 037）。
      service の runtime SA に Vertex AI（`roles/aiplatform.user`）/ Secret Manager 参照（方式 B）が
      付与済みであること（issue 017/018 前提）を確認するのみ。

### テスト

- [ ] api（`backend/api/tests/`）: `POST .../agents/{kind}/run` が `202` + `job_id` を返し、`Job` が
      `QUEUED` で作成され `MockTaskDispatcher.dispatch` が 1 回呼ばれること（`test_stack.py` パターン）。
- [ ] api: `GET .../agents/activities?kind=` / `.../activities/{id}` / `.../pipelines/{id}` が
      `schemas.ts` 同形（snake_case）の JSON を返すこと。retry が失敗ノードのみ受理し新 Job を enqueue すること
      （`retryable=false` / 未存在は 409/404）。`OrgScope` で非メンバーが 403 になること。
- [ ] service（`backend/service/tests/`）: `agent_loop.process` のパイプラインテスト
      （検知結果テーブル・Gemini・GitHub を **モック**）。ステージ進行で `agent_pipeline.stages` が更新され、
      `narrative_step` / `narrative_evidence` が永続化されること。再配送（at-least-once）で二重生成されない
      冪等性（`worker.run_task` 経由）。`repay` の sub-enqueue が ADR どおり起動されること。
- [ ] frontend: `agent-store` のユニットテスト（`loadMock` の実 API 化・`retry` / `tick` の API 呼び出し、
      API モック）。`agentActivitySchema` / `agentPipelineSchema` の parse が通ること。

## 完了条件

- `POST .../agents/{kind}/run` が `202` + `job_id` を返し、api リクエストはループ完了を待たずに即返ること。
- service が api リクエスト外で 5 ステージループを実行し、`agent_pipeline` / `agent_activity` /
  `narrative_step` / `narrative_evidence` を Cloud SQL に逐次永続化すること（partial 状態を配信できる）。
- `GET .../agents/activities` / `.../activities/{id}` / `.../pipelines/{id}` / `/agents/profiles` が
  `schemas.ts:381-456` の Zod（`AgentActivity` / `AgentPipeline` / `AgentProfile`）と一致する snake_case JSON を返すこと。
- 失敗ノードに対し `POST .../nodes/{node_id}/retry` が新 Job を enqueue し、ノード status が遷移すること。
- `evidence.href` のクロスドメインリンク（例 `/matrix/{debt_id}`）が、存在する負債 id に対してのみ
  組み立てられること（検証規約。後述「対象外・保留」も参照）。
- フロント `agent-store.svelte.ts` の `loadMock` / `tick` / `retry` が実 API 化され、Twin Agent 活動ビューが
  実データで描画されること（`MOCK_*` への直接依存が無いこと）。
- sub-enqueue / 直接呼びの線引きが `docs/adr/` に ADR として記されていること。
- バックエンド: `cd backend && uv run --directory api pytest`（service / shared も `--directory`）/
  `uv run ruff check shared/shared api/app service/service && uv run ruff format --check ...` /
  `uv run ty check shared/shared api/app service/service` が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語、Keep a Changelog）に `Added`（Twin Agent 自律ループパイプライン /
  agent_pipeline・agent_activity・narrative_step・narrative_evidence テーブル / agents 配信 API）を追記。

## 対象外・保留

- **個別の検知・KC・採点・PR 生成ロジック**: issue 028 / 029 / 030 / 033 / 034 が所有。本 issue は束ねるのみ。
- **ライブ SSE / WebSocket**: MVP はポーリング（`getPipeline` 再取得 + `GET /jobs/{id}`）。逐次 push は将来。
- **定期スキャン（Cloud Functions/Scheduler/Pub-Sub）**: issue 037。本 issue は手動トリガーのみ。
- **AI 生成痕跡の確率算出ロジック本体**（例 `agent-activity.ts:68` の「推定 92%」）: 028/030 の
  `ai_generation_prob` を **読むだけ**。算出式は本 issue で確定しない。
- **`evidence.href` の宛先ページ実在保証**: 本 issue は Matrix（031）等のルート形に合わせて href を組み立て、
  参照先 id（`debt_id` 等）の存在チェックに留める（リンク先 UI は別ドメイン）。
- **KC / priority 等の製品式**: 011 本文に無く、検知系 issue（007-010 / 028-030）が出所。本 issue で再定義しない（捏造しない）。

## 参考

- 関連 issue
  - `docs/issue/011-agents-narrative-activity-stream.md` — フロント活動ビュー（Zod 契約・モックの出所、§4.2 考古学 / §6.5 ナラティブ）
  - `docs/issue/016-async-task-queue-cloud-tasks.md` / `docs/issue/018-stack-analysis-async-job-on-service.md` — 非同期基盤・パイプライン移設パターン（雛形）
  - `docs/issue/028-...` / `029-...` / `030-...` / `033-...` / `034-...` — 束ねる検知/算出/返済/採点（depends_on）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — `evidence.href` の `/matrix/{debt_id}` 宛先
  - `docs/issue/037-backend-periodic-scan-cloud-functions.md` — 定期スキャン（自律ループの定期トリガー）
- フロント契約 / モック
  - `frontend/src/lib/api/schemas.ts:381-456` — `agentKind/Profile/Status/NarrativeEvidence/Step/Activity/PipelineNode/Stage/Pipeline` スキーマ + 型
  - `frontend/src/lib/mocks/agent-activity.ts` — `MOCK_PROFILES`（:6）/ `MOCK_ACTIVITIES`（:23）/ `MOCK_PIPELINES`（:126）、href 例（:112）
  - `frontend/src/lib/stores/agent-store.svelte.ts` — `loadMock`（:16）/ `retry`（:31）/ `tick`（:40）= 実 API 化対象
  - `frontend/src/lib/api/client.ts:257-276` — `analyzeStack` / `getJob` / `getStack`（新規 agent 関数の雛形）
- 既存 backend（雛形・流用）
  - `backend/api/app/api/v1/stack.py:105-143`（202 enqueue）/ `:36-65`（snake_case Out）
  - `backend/api/app/api/v1/jobs.py:57-77`（ポーリング配信・result_data 持ち上げ）
  - `backend/api/app/api/v1/projects.py:18-`（`/orgs/{slug}/projects/{project_slug}` ルート形）/ `deps.py:64-65`（`OrgScope`/`OrgAdminScope`）
  - `backend/api/app/api/v1/router.py:8-20`（ルーター include）
  - `backend/shared/shared/enums.py:11-16`（`JobType`）/ `models/tech_stack.py:19-44`（ORM 雛形）/ `models/__init__.py:3-6`（re-export）
  - `backend/shared/shared/schemas/stack_analysis.py:45-77`（`GitHubRef` / Request/Result 雛形）/ `schemas/job.py`（`JobRequestBase`/`JobResultBase`）
  - `backend/service/service/pipelines/stack_analysis.py`（`process(request, ctx)` 雛形・`_vertex_model_name`）/ `registry.py:15-18`（三つ組登録）
  - `backend/service/service/services/`（`github_git_client.py` / `github_app.py` 方式 B / `gemini_stack_service.py` Vertex+ADC）
  - `backend/shared/shared/worker.py:32`（`run_task` 冪等）/ `shared/pipelines/context.py:19`（`PipelineContext`）
  - `backend/api/app/alembic/versions/0005_add_jobs.py`（マイグレーション雛形・naming convention）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — snake_case 配信、PATCH 規約、Annotated DI param 順序厳守、
    `models/__init__.py` import 順、JobType 追加、router 登録、Vertex AI + ADC（API キー不使用）、Secret Manager / 方式 B、
    ゲート（`uv run ruff/ty/pytest` / `bun run check/lint/test:unit`）、`CHANGELOG.md`（日本語）
