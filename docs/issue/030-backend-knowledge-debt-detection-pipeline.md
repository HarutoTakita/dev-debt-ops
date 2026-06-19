# 知識負債検知パイプラインを service に追加する（AI生成/著者離脱/未レビュー）

## 概要

フロントの負債レジストリ / Matrix のうち「知識負債（Knowledge Debt）」側は、現状すべて
`frontend/src/lib/api/mock/debts.ts` の `MOCK_DEBTS`（`kind: "knowledge"` 行、`debts.ts:33,53,116`）を
読んでいるだけで、裏側の検知ロジックも永続化テーブルも存在しない。`client.listDebts` / `client.getDebt`
（`frontend/src/lib/api/client.ts:311` / `:317`）も TODO で mock を返している。

本 issue は、この **知識負債の検知（裏側）** を service の非同期パイプラインとして新設する。
重い解析（git 履歴に基づく著者離脱・未レビュー判定 + Gemini による AI 生成痕跡推定）は service 側の
`process(request, ctx)`（雛形 `backend/service/service/pipelines/stack_analysis.py:361`）に載せ、api は
`POST .../detect-knowledge-debts` で `202 {job_id}` を返す enqueue + ポーリングに徹する
（Issue 018 の `stack_analysis` パターンを完全踏襲）。検知結果は shared の **新規 `knowledge_debts` テーブル**
と、code / knowledge 両負債に紐付く **`assigned_developers` テーブル** に永続化する。KC（Knowledge Coverage）の
本算出は **Issue 029** が所有し、本 issue はその結果（`file_kc`）を join して `knowledge_coverage` と
担当者の `coverage` / `certified_via` を埋める。

> 本 issue の **責務は「知識負債の検知 + 永続化」まで**。検知済みデータを集計して
> `debtListSchema` / `debtItemSchema`（`schemas.ts:270-274`）形で配信する一覧 / 詳細 / アクション API は
> **Issue 031** が所有する。KC の算出式・閾値も **Issue 029** が所有し、本 issue は join するのみ（捏造しない）。

## 背景・目的

### 現状（フロントだけ・裏側ゼロ）

- `frontend/src/lib/api/schemas.ts:251-268` の `knowledgeDebtSchema` が API レスポンス契約として確定済み
  （`reason` / `severity` / `status` / `related_adr` / `code_snippet` / `code_debt_score` /
  `knowledge_coverage` / `ai_generation_prob` / `estimated_repay_hours` / `assigned_developers` を snake_case で保持）。
- `frontend/src/lib/api/mock/debts.ts` の `kind:"knowledge"` 行（`debts.ts:33,53,116`、`repo:"demo"`）が
  この形の固定値を持ち、`client.ts:311` の `listDebts` は `applyFilterSort(MOCK_DEBTS, ...)` を返すだけ（実 API は TODO）。
- バックエンドには `knowledge_debts` / `assigned_developers` テーブルも検知パイプラインも存在しない
  （既存 shared モデルは `Job` / `TechStack` のみ。`backend/shared/shared/models/__init__.py:3-4`）。

### 製品セマンティクス（出所）

独立した仕様書はリポジトリに存在せず、`docs/issue/008-matrix-debt-registry-drilldown.md` と
`frontend/src/lib/api/schemas.ts` を契約の正とする。

- **知識負債の種別（reason）:** `ai_generated`（AI 生成）/ `author_left`（著者離脱）/ `no_review`（未レビュー）/ `other`
  （`schemas.ts:256` `knowledgeDebtSchema.reason`、mock `debts.ts:36`(`no_review`),`:58`(`author_left`),`:119`(`ai_generated`)）。
- **ステータス:** `open` / `in_progress` / `resolved`（`schemas.ts:258`。code 側の `in_pr` / `dismissed` は **持たない**）。
- **related_pr を持たない:** `knowledgeDebtSchema` には `related_adr`（nullable）のみで `related_pr` は無い（`schemas.ts:260`）。
- **`archaeology_notes` を契約上は持たない:** `codeDebtSchema`（`schemas.ts:241`）にはあるが `knowledgeDebtSchema`
  には `archaeology_notes` フィールドが無い（mock の knowledge 行 `debts.ts:33-52,53-71,116-130` にも存在しない）。
  検知根拠の文章は **検知側の補助情報** として `knowledge_debts` に持たせてよいが、`knowledgeDebtSchema` の配信契約には
  含めない（配信整形は Issue 031 が schema に厳密一致させる）。
- **担当者の理解者 / 形式レビューのみの区別（§5.1 KC・§5.5 返済認定、`008:308-311`）:**
  `certified_via` が `quiz` / `authorship` かつ `coverage >= 0.7` → 「理解者」（実線リング・緑系）／
  `review` または `coverage < 0.4` → 「形式レビューのみ / 未理解」（破線リング・灰系）。
  本 issue はこの判定の **入力となる `coverage`（= KC(file,dev)）と `certified_via` を確定して永続化** する
  （mock `debts.ts:48-51` が `carol`=`authorship`/`0.75`=理解者・`dave`=`review`/`0.31`=形式レビューのみ、を例示）。
- **二軸負債モデル（§2.3）:** `code_debt_score`（縦・高=汚い）× `knowledge_coverage`（横・高=皆理解=KC(file)）。
  knowledge 行も `code_debt_score` / `knowledge_coverage` / `ai_generation_prob` / `estimated_repay_hours` を持つ
  （`schemas.ts:262-265`）。

### 設計方針

重い解析（git 履歴解析・AI 生成痕跡の Gemini 推定・KC join）は service の非同期パイプライン
（Issue 016/018 パターン）に載せ、api は enqueue + ポーリングに徹する（配信は Issue 031）。
GitHub トークンは **方式 B**（`installation_id` のみキュー搬送、service が Secret Manager から mint。
`backend/shared/shared/schemas/stack_analysis.py:45-55` `GitHubRef`）を踏襲する。

## 前提 issue（depends_on）

- **Issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file`
  共有テーブル、`JobType` 拡張規約（lowercase snake_case = queue path）、pgvector 拡張。本 issue の
  `knowledge_debts` は `run_id`（FK → `analysis_run.id`）でスナップショット軸に紐づき、ファイル同一性は
  `repo_file`（`(run_id, path)`）を参照する前提とする。
- **Issue 027** `docs/issue/027-backend-github-history-client-extension.md` — `GitHubGitClient` への commit 履歴 /
  blame / PR レビューメタ取得拡張と authorship ↔ `users.id` 突合ユーティリティ。著者離脱・未レビュー判定の git
  アクセス基盤を提供する（現状 `backend/service/service/services/github_git_client.py` は tree / contents のみ）。
- **Issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc`（KC(file,dev) / KC(file) /
  `certified_via` / `mastery`）。本 issue は `knowledge_coverage`（= KC(file)）と `assigned_developers.coverage`
  （= KC(file,dev)）/ `certified_via` を `file_kc` から join して埋める。

> 026/027/029 が確定するまで `run_id` / `repo_file` 参照・`file_kc` の具体カラム名は仮であり、各 issue の
> 最終形に合わせて整合させる（捏造しない）。`assigned_developers` テーブルは Issue 028（コード負債）と共有するため、
> どちらの Alembic で作成するか・作成順を 028 と調整する（重複作成しない）。

## データモデル

新規テーブルは **shared ORM**（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）に置き、
Alembic マイグレーションは **api が所有**（`backend/api/app/alembic/versions/`、連番は 0006 以降。
雛形 = `0003_add_tech_stacks.py` / `0005_add_jobs.py`）。service は `backend/service/service/db.py` の薄い
セッションで DML するのみ。id は `shared` 軽量方針に合わせ `uuid.uuid4` default、`DateTime(timezone=True)`
（`backend/shared/shared/models/tech_stack.py:19-45` 踏襲）。

### 新規: `knowledge_debts`（`backend/shared/shared/models/knowledge_debt.py`）

`code_debts`（Issue 028 が所有）と同構造だが、knowledge 固有の差分を持つ。`schemas.ts:251-268`
`knowledgeDebtSchema` に対応：

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`default_factory=uuid.uuid4`、PK） | `knowledgeDebtSchema.id`。`tech_stack.py:28` と同方式 |
| `project_id` | `uuid.UUID`（FK → `projects.id`） | プロジェクト単位（1 project = 1 repo） |
| `run_id` | `uuid.UUID`（FK → `analysis_run.id`、026） | どのスナップショットで検知したか。026 確定後に名称整合 |
| `file_path` | `str` | `schemas.ts:254`（File join 済み平坦化、`repo_file` と join 可） |
| `repo` | `str` | `schemas.ts:255`（mock は `repo:"demo"`、`debts.ts:35`） |
| `reason` | enum `ai_generated`/`author_left`/`no_review`/`other` | `schemas.ts:256` |
| `severity` | enum `critical`/`high`/`medium`/`low` | `severitySchema`（`schemas.ts:220`）。float→enum 量子化（後述） |
| `status` | enum `open`/`in_progress`/`resolved` | `schemas.ts:258`（`dismissed` 無し）。初期値 `open` |
| `detected_at` | `datetime`（tz aware） | `schemas.ts:259`（iso offset） |
| `related_adr` | `str \| None` | `schemas.ts:260`（`related_pr` は **持たない**） |
| `code_snippet` | `str` | `schemas.ts:261`（詳細ビュー表示用） |
| `code_debt_score` | `float`（0..1） | `schemas.ts:262` |
| `knowledge_coverage` | `float`（0..1） | `schemas.ts:263`。= KC(file)、Issue 029 `file_kc` から join して埋める |
| `ai_generation_prob` | `float`（0..1） | `schemas.ts:264`。Gemini 推定 |
| `estimated_repay_hours` | `float` | `schemas.ts:265` |
| `detection_notes` | `str`（**配信契約外**） | 検知根拠（「PR で AI 生成・自動 approve」「作者離脱・最終コミット 540 日前」等）。`knowledgeDebtSchema` には無いフィールドなので配信時は出さない（Issue 031） |

> `assigned_agent`（`literal "knowledge_debt"`、`schemas.ts:266`）は固定リテラルなので列にせず、配信時に
> api が付与する（Issue 031）。`severity` の量子化しきい値（float→4 段 enum）は本 issue で確定する（後述）。

### 新規: `assigned_developers`（`backend/shared/shared/models/assigned_developer.py`、code/knowledge 両方に紐付く）

`schemas.ts:224-228` `assignedDeveloperSchema` に対応。code（028）/ knowledge（030）両 debt に紐付くため
**判別カラム方式**（`debt_kind` + `debt_id`）を採る（多態 FK は SQLModel で扱いづらく避ける）。

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`uuid4`、PK） | |
| `debt_kind` | enum `code`/`knowledge` | どちらの debt 表を指すか（判別カラム。`debtKindSchema` `schemas.ts:221`） |
| `debt_id` | `uuid.UUID` | `code_debts.id` または `knowledge_debts.id`（DB FK は張らず判別カラムで解決） |
| `github_handle` | `str` | `schemas.ts:225`（mock `carol`/`dave`/`erin` 等、`debts.ts:49-50`） |
| `coverage` | `float`（0..1） | `schemas.ts:226` = KC(file,dev)、Issue 029 `file_kc`（dev_id 指定行）から埋める |
| `certified_via` | enum `quiz`/`authorship`/`review` | `schemas.ts:227`（`certifiedViaSchema` `:222`）。029 `file_kc.certified_via` を写す |

> `(debt_kind, debt_id)` に index を張る（配信 031 が debt ごとに担当者を join するため）。
> 理解者 / 形式レビューの区別（§5.5、`008:308-311`）は `certified_via` + `coverage` から **配信側（031）または UI**
> が判定する。本 issue は `coverage` / `certified_via` を **正しく埋める** ことが責務（判定式の入力を確定）。

### severity 量子化しきい値（本 issue で確定）

`severitySchema`（`schemas.ts:220`）は 4 段 enum だが、検知器が出す raw スコアは float。doc 008 §7.1 注記
（`docs/issue/008-matrix-debt-registry-drilldown.md:180`「しきい値は本実装で確定」）に従い、`code_debt_score`
（0..1、高=汚い）を以下のバンドで量子化する（Issue 028 の `code_debts` と同表に揃える。製品判断として明示。
外部仕様書に式は無い＝捏造しない）：

| `code_debt_score` | `severity` |
|---|---|
| `>= 0.75` | `critical` |
| `0.50 – 0.75` | `high` |
| `0.25 – 0.50` | `medium` |
| `< 0.25` | `low` |

### models/__init__.py への登録

`backend/shared/shared/models/__init__.py`（現状 `Job` / `TechStack` を re-export、`:3-6`）に
`KnowledgeDebt` / `AssignedDeveloper` を追加（import 順は app→shared 規約。autogenerate のため）。

## API（`/api/v1/...`）

api は **enqueue + ポーリング** のみを担う。配信（一覧 / 詳細 / アクション）は **Issue 031** が所有する。

### `POST /api/v1/orgs/{slug}/projects/{project_slug}/detect-knowledge-debts` → `202`

- `stack.py::analyze_stack`（`backend/api/app/api/v1/stack.py:105-143`）を雛形にコピーし、`job_type` を
  新 `JobType.KNOWLEDGE_DEBT_DETECTION` に変える。レスポンスは既存 `JobEnqueuedOut`
  （`backend/api/app/schemas/job.py`、`{job_id, status}`）を流用。
- ルーティング: `projects.py` の `/orgs/{slug}/projects/{project_slug}/...` 配下に揃える（プロジェクト単位）。
  `projects.py:42` の実ルート形・`OrgScope`（`backend/api/app/api/deps.py:64`）に合わせる。新ルーターは
  `backend/api/app/api/v1/router.py`（`:13-20`）に `include_router` を追加する。
- 認可: `OrgScope`（org member）を基本とし、`POST`（書込トリガ）を admin 限定にするかは Issue 028 の
  `detect-debts` と揃える（設計判断として明記）。**Annotated DI param 順序を変更しない**
  （CLAUDE.md「`Annotated[T, Depends(f)]` deps の宣言順序を変えない」）。
- payload: 方式 B = `{ owner, repo, branch, project_id, run_id?, requested_by, github: { installation_id } }`
  （`stack.py:128-134` 形。`installation_id` のみ＝秘密はキューに載せない）。
- `enqueue_job(session, dispatcher, blob_client, job_type=JobType.KNOWLEDGE_DEBT_DETECTION, payload=..., created_by=current_user.id)`
  （`backend/api/app/services/job_orchestrator.py`）を呼び、`Job.project_id` に `project_slug` 解決後の `project.id`
  を設定する。
- ポーリング: 既存 `GET /api/v1/jobs/{id}`（`backend/api/app/api/v1/jobs.py:47`）をそのまま流用。
  検知完了の確認は `job.status === "COMPLETED"`（大文字 enum、`backend/shared/shared/enums.py:22-25`）。
  `Job.result_data` には検知サマリ（件数・reason 別件数・trace）が入る。

> 配信（`GET .../debts` → `debtListSchema`、`GET .../debts/{id}` → `debtItemSchema`、
> `PATCH .../debts/{id}` で `status` 更新）は **本 issue では実装しない**（Issue 031）。

## パイプライン・非同期

### JobType 追加（`backend/shared/shared/enums.py:11-16`）

`JobType` に追加（`STACK_ANALYSIS` の隣、lowercase snake_case = queue / task path 名 `knowledge-debt-detection`）：

```python
KNOWLEDGE_DEBT_DETECTION = "knowledge_debt_detection"  # 知識負債検知（issue 030）
```

### request / result スキーマ（`backend/shared/shared/schemas/knowledge_debt_detection.py`）

`stack_analysis.py:58-77` を雛形に、`JobRequestBase` / `JobResultBase`（`backend/shared/shared/schemas/job.py:12,20`）
を継承し、`GitHubRef`（`stack_analysis.py:45-55`、方式 B）を再利用：

- `KnowledgeDebtDetectionRequest(JobRequestBase)`: `owner` / `repo` / `branch: str = "main"` / `github: GitHubRef` /
  `project_id: str` / `run_id: str | None = None` / `requested_by: str`（監査用）。
- `KnowledgeDebtDetectionResult(JobResultBase)`: `project_id: str` / `detected_count: int` /
  `reasons: dict[str, int]`（reason 別件数）/ `trace: list[str]`（解析ステップ）。
  検知本体は DB（`knowledge_debts` / `assigned_developers`）へ upsert するため、`result_data` には
  サマリ（件数・trace）のみを書く（`StackAnalysisResult` が `languages`/`categories` を詰めるのと同型だが、
  本 issue は行が多いので件数サマリに留める。`Job.result_data` は camelCase / `by_alias=True`、
  `stack_analysis.py` ヘッダ参照）。

### registry 三つ組登録（`backend/service/service/registry.py:15-18`）

`PIPELINES` に追加（`stack_analysis` の隣、`:17` 同型）。重い依存（git 履歴/Vertex/GitHub）は service のみに置き
shared/api に漏らさない（`registry.py:1-8` の方針）：

```python
JobType.KNOWLEDGE_DEBT_DETECTION.value: (
    KnowledgeDebtDetectionRequest, KnowledgeDebtDetectionResult, knowledge_debt_detection.process,
),
```

### `process(request, ctx)`（`backend/service/service/pipelines/knowledge_debt_detection.py`）

`stack_analysis.py::process`（`backend/service/service/pipelines/stack_analysis.py:361-389`）を雛形に、
`ctx.session`（`backend/shared/shared/pipelines/context.py` `PipelineContext`）で DML する：

1. `ctx.session` が `None` なら `RuntimeError`（`stack_analysis.py:368`）。
2. 方式 B でトークン mint（`stack_analysis.py:332-342` `_mint_installation_token` 流用 =
   `service.services.github_app.GitHubAppService`）。
3. **Issue 027 拡張版 `GitHubGitClient`** で commit 履歴 / blame / PR レビューメタを取得し判定する：
   - `author_left`: ファイルの主要 author が org member から離脱（最終コミットからの経過・authorship ↔ `users.id` 突合）。
   - `no_review`: PR がレビューなし / 自動 approve でマージされた痕跡。
4. **`gemini_stack_service`（Vertex AI + ADC、`stack_analysis.py:44-57` の `_vertex_model_name` =
   `projects/` で始まる model 名で ADK が Vertex+ADC を自動選択）** で `ai_generated`（AI 生成痕跡）の
   `ai_generation_prob`（0..1）を推定し `detection_notes` の根拠文を生成する。
5. 上記から `KnowledgeDebt` 行を生成し、`reason` / `severity`（float→enum 量子化）/ `detection_notes` /
   `code_snippet` / `code_debt_score` / `ai_generation_prob` / `estimated_repay_hours` を埋めて upsert
   （`stack_analysis.py:214-231` の `pg_insert(...).on_conflict_do_update` パターン。`(project_id, file_path, reason)`
   等のユニーク制約で冪等再検知）。
6. **Issue 029 `file_kc` を join** して `knowledge_coverage`（= KC(file)）を埋め、ファイル × dev の `file_kc`
   （dev_id 指定行）から `assigned_developers`（`coverage` / `certified_via`）を生成する。理解者 / 形式レビューの
   区別（`008:308-311`）の入力をここで確定する。`file_kc` が未算出（029 未完）の場合は `knowledge_coverage` を
   暫定値（0.0 か NULL 相当）で埋め、配信時 join で上書きされる前提とする。
7. `KnowledgeDebtDetectionResult` を返す（`shared.worker.run_task` が `Job.result_data` へ冪等に書く）。

> 冪等性 / Job ライフサイクル（PROCESSING → COMPLETED/FAILED）は `shared.worker.run_task` が吸収する
> （`stack_analysis.process` と同様に DML のみ書く）。ADK エージェント化（`Runner` 方式）にするか手続き直叩きにするかは実装判断。

### 定期スキャン

知識負債の定期再検知は CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub）」に従い、
Cloud Scheduler → Pub/Sub → Cloud Functions で project を巡回して本 Job を enqueue する。基盤の Terraform は
**Issue 037** が所有（本 issue では追加しない）。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `models/knowledge_debt.py` に `KnowledgeDebt` ORM を新設（雛形 `tech_stack.py:19-45`。上表の列・enum・`detection_notes`）。
- [ ] `models/assigned_developer.py` に `AssignedDeveloper` ORM を新設（`debt_kind` 判別カラム + `(debt_kind, debt_id)` index）。
      Issue 028 と共有のため、作成は本 issue と 028 のどちらかに寄せ重複定義を避ける。
- [ ] `models/__init__.py:3-6` に `KnowledgeDebt` / `AssignedDeveloper` を re-export 追加（import 順 app→shared 規約）。
- [ ] `enums.py:16`（`STACK_ANALYSIS` の隣）に `KNOWLEDGE_DEBT_DETECTION = "knowledge_debt_detection"` を追加。
- [ ] `enums.py` に `Severity` / `KnowledgeDebtReason` / `KnowledgeDebtStatus` / `DebtKind` の StrEnum を追加
      （`severitySchema`/`knowledgeDebtSchema.reason`/`.status`/`debtKindSchema`、`schemas.ts:220-222,256,258` と値一致）。
      `Severity` / `DebtKind` は Issue 028 と共有（重複定義しない）。
- [ ] `schemas/knowledge_debt_detection.py` を新設（`stack_analysis.py:58-77` 雛形。Request/Result、`GitHubRef`
      再利用・`JobRequestBase`/`JobResultBase` 継承）。

### api（`backend/api/app/`）

- [ ] `alembic/versions/0006_add_knowledge_debts.py`（または 028 と調整した後続番号）で `knowledge_debts` /
      `assigned_developers` を作成（雛形 `0003_add_tech_stacks.py` / `0005_add_jobs.py`、`base.py` の naming convention）。
      `(project_id, file_path, reason)` 等のユニーク制約で冪等 upsert を可能にする。`code_debts`（028）との作成順 /
      リビジョン依存を調整する。
- [ ] `api/v1/knowledge_debts.py`（または 028/031 と統合した `debts.py`）に
      `POST /orgs/{slug}/projects/{project_slug}/detect-knowledge-debts` → `202 JobEnqueuedOut` を実装
      （雛形 `stack.py:105-143`、`OrgScope` `deps.py:64`、`JobEnqueuedOut` 流用、Annotated DI param 順序厳守）。
- [ ] `api/v1/router.py:13-20` に新ルーターを `include_router`（`projects_router` の隣）。

### service（`backend/service/service/`）

- [ ] `pipelines/knowledge_debt_detection.py` の `process(request, ctx)` を新設
      （雛形 `stack_analysis.py:361-389`、方式 B mint `:332-342`、`ctx.session` upsert `:214-231`）。
- [ ] git 履歴 / blame / PR レビュー取得は **Issue 027 拡張版 `GitHubGitClient`**
      （`service/service/services/github_git_client.py`）を利用。authorship ↔ `users.id` 突合は 027 のユーティリティ。
- [ ] AI 生成痕跡推定は `service/service/services/gemini_stack_service.py`（Vertex AI + ADC、`stack_analysis.py:44-57`）を流用 / 拡張。
- [ ] `knowledge_coverage` / `assigned_developers.coverage` / `certified_via` を **Issue 029 `file_kc`** から join して埋める。
- [ ] `registry.py:15-18` の `PIPELINES` に三つ組を登録（`:17` 同型）。

### frontend（`frontend/src/`）

- [ ] **`client.listDebts`（`client.ts:311`）/ `getDebt`（`:317`）の mock 差し替えは Issue 031（配信 API）で行う**
      （本 issue は検知トリガ配線まで。連携先として明示）。
- [ ] 検知トリガ UI を足す場合は `client.ts` に `detectKnowledgeDebts(orgSlug, projectSlug)` を追加し、
      `analyzeStack`（`client.ts:257`）と同型で `202 {job_id}` を返し、既存 `getJob`（`client.ts:265`）ポーリングに
      合流させる（`analyzeStackJobSchema` `schemas.ts:157` / `jobStatusSchema` `:163` を流用）。

### infra

- [ ] 定期スキャン enqueue（Cloud Functions/Pub-Sub での巡回）は **Issue 037** に委譲（本 issue では追加しない）。

### test

- [ ] api（`backend/api/tests/`）: `POST detect-knowledge-debts` が `202` + `job_id` を返し、
      `Job(QUEUED, type=knowledge_debt_detection)` が作成され、`MockTaskDispatcher.dispatch` が 1 回呼ばれること
      （018 のテスト方針に倣う。エージェント / 解析を api リクエスト内で直接実行しない）。
- [ ] service（`backend/service/tests/`）: `knowledge_debt_detection.process` のパイプラインテスト
      （`GitHubGitClient` / Gemini を **モック**）。`author_left` / `no_review` / `ai_generated` 各 reason で
      `KnowledgeDebt` + `assigned_developers` が upsert されること。再配送（at-least-once）で二重生成されない冪等性。
      方式 B の token mint 経路。severity 量子化の境界値（`>=0.75` 等）。
- [ ] service: `file_kc`（029）を join して `knowledge_coverage` / `coverage` / `certified_via` が埋まること
      （理解者 = `quiz`/`authorship` かつ `coverage>=0.7`、形式レビュー = `review` または `coverage<0.4` の入力が正しいこと、`008:308-311`）。

## 完了条件

- `POST /api/v1/orgs/{slug}/projects/{project_slug}/detect-knowledge-debts` が **`202` + `job_id`** を即返し、
  検知は service 側で api リクエスト外に実行される（api ワーカーが解析でブロックされない）。
- service が git 履歴（027）+ Gemini で `author_left` / `no_review` / `ai_generated` を判定し、
  `knowledge_debts`（`schemas.ts:251-268` に対応する列）+ `assigned_developers`（`schemas.ts:224-228`）を
  Cloud SQL に永続化する（`Job` 行も `shared.worker.run_task` 経由で `COMPLETED`/`FAILED` に直接更新、api コールバック・Pub/Sub 無し）。
- `knowledge_coverage`（KC(file)）と `assigned_developers.coverage`（KC(file,dev)）/ `certified_via` が
  Issue 029 `file_kc` から join されて埋まり、理解者 / 形式レビュー判定（`008:308-311`）の入力が確定している。
- `severity` が量子化 enum で書かれ、`status` 初期値が `open` であること（`knowledgeDebtSchema` に整合）。
- `GET /api/v1/jobs/{id}` で検知ジョブの `status` と件数サマリ（reason 別件数）がポーリングできる。
- `shared.worker.run_task` 経由の冪等性（再配送で二重生成なし）が test で確認できる。
- バックエンド: `cd backend && uv run ruff check shared/shared api/app service/service && uv run ruff format --check shared/shared api/app service/service`
  / `uv run ty check shared/shared api/app service/service` / `uv run --directory shared pytest` / `--directory api pytest` / `--directory service pytest` が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語, Keep a Changelog）に `Added`（知識負債検知パイプライン / `knowledge_debts` /
  `assigned_developers` テーブル / `knowledge_debt_detection` JobType）を追記。

## 対象外・保留

- **配信 API（一覧 / 詳細 / アクション）:** `GET .../debts`（`debtListSchema`、`schemas.ts:271`）/
  `GET .../debts/{id}`（`debtItemSchema`、`schemas.ts:270`）/ `PATCH .../debts/{id}`（`dismissDebt` 相当は
  knowledge には `dismissed` 無し）と `client.listDebts`/`getDebt`（`client.ts:311,317`）の mock 差し替え、
  フィルタ/ソートの DB クエリ化（`applyFilterSort`/`SEVERITY_RANK`）は **Issue 031**。
- **KC 本算出:** KC(file,dev) / KC(file) / `certified_via` / `mastery` の算出式・閾値は **Issue 029** が所有。本 issue は join のみ。
- **コード負債検知（duplicate/dead/complexity）:** **Issue 028**。`code_debts` テーブルもそちらが新設し、
  `assigned_developers` は本 issue が新設して両者で共有する（作成順を 028 と調整）。
- **返済 PR 生成 / クイズ生成:** knowledge 負債の返済体験は Issue 033（PR）/ 034（quiz）/ 035（learning）。本 issue は検知まで。
- **`business_impact` 第 3 軸**の取り込み（doc 008 §3 注記）— 将来。
- **pgvector による重複検知 / 概念マッピング:** 拡張有効化は Issue 026、本実装は将来。
- **定期スキャン基盤（Cloud Functions/Pub-Sub）:** **Issue 037**。

## 参考

- 関連 issue
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 非同期パイプライン雛形（enqueue + 202 + ポーリング、方式 B）
  - `docs/issue/008-matrix-debt-registry-drilldown.md` — 知識負債の reason / status / 理解者・形式レビュー判定（§5.5, `:308-311`）/ severity 量子化（§7.1, `:180`）
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md`（`analysis_run`/`repo_file`/JobType 規約・前提）
  - `docs/issue/027-backend-github-history-client-extension.md`（git 履歴クライアント拡張・authorship 突合・前提）
  - `docs/issue/028-backend-code-debt-detection-pipeline.md`（`code_debts` / `assigned_developers` 共有・severity 量子化を揃える）
  - `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md`（`file_kc` 本算出・前提）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md`（配信 API、`client.listDebts`/`getDebt` 差し替え）
  - `docs/issue/037-backend-periodic-scan-cloud-functions.md`（定期スキャン）
- 契約（フロント）
  - `frontend/src/lib/api/schemas.ts:251-268`（`knowledgeDebtSchema`）/ `:224-228`（`assignedDeveloperSchema`）/
    `:220-222`（`severitySchema`/`debtKindSchema`/`certifiedViaSchema`）/ `:270-274`（`debtItemSchema`/`debtListSchema`）
  - `frontend/src/lib/api/mock/debts.ts:33,53,116`（`MOCK_DEBTS` の `kind:"knowledge"` 行、`repo:"demo"`、`assigned_developers` 例 `:48-51`）
  - `frontend/src/lib/api/client.ts:311,317`（`listDebts`/`getDebt`、現状 mock。差し替えは 031）/ `:257,265`（`analyzeStack`/`getJob` 規約）
- 既存 backend（雛形・流用）
  - `backend/api/app/api/v1/stack.py:105-143`（`analyze_stack` enqueue 202 雛形）/ `api/v1/router.py:13-20`（ルーター登録）/
    `api/v1/projects.py:42`（`/orgs/{slug}/projects/{project_slug}` 形）/ `api/deps.py:64`（`OrgScope`）/ `api/v1/jobs.py:47`（ポーリング）
  - `backend/shared/shared/enums.py:11-16`（`JobType` 追加点）/ `:19-25`（`JobStatus` 大文字）
  - `backend/shared/shared/schemas/stack_analysis.py:45-55,58-77`（`GitHubRef` / Request/Result 雛形）/ `schemas/job.py:12,20`（`JobRequestBase`/`JobResultBase`）
  - `backend/shared/shared/models/tech_stack.py:19-45`（ORM 雛形）/ `models/__init__.py:3-6`（re-export 順）
  - `backend/service/service/pipelines/stack_analysis.py:44-57,214-231,332-342,361-389`（`_vertex_model_name` / upsert / 方式 B mint / `process`）/ `service/service/registry.py:15-18`（PIPELINES 登録）
  - `backend/api/app/services/job_orchestrator.py`（`enqueue_job`）/ `backend/api/app/schemas/job.py`（`JobEnqueuedOut`）
  - `backend/api/app/alembic/versions/0003_add_tech_stacks.py` / `0005_add_jobs.py`（次番 `0006`）
  - `backend/service/service/services/github_app.py`（installation token mint）/ `github_git_client.py`（tree/contents、027 で拡張）/ `gemini_stack_service.py`（Vertex AI + ADC）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — Vertex AI + ADC（API キー不使用）/ Secret Manager 必須 / 方式 B / Annotated DI param 順序厳守 /
    `models/__init__.py` import 順（app→shared）/ `JobType` 追加 / `router.py` ルーター登録 / snake_case 配信 / PATCH 部分更新 /
    ゲート（`uv run ruff`/`ty`/`pytest`、`bun run check`/`lint`/`test:unit`）/ `CHANGELOG.md`（日本語）
