# Overview 二軸集計 API と負債レジストリ配信/アクション API を実装する

## 概要

Overview 二軸ダッシュボードと負債レジストリ / Matrix は、フロントが完成済み契約
（`frontend/src/lib/api/schemas.ts` の `overviewSchema` / `debtListSchema` / `debtItemSchema`）を持ちながら、
**配信する裏側 API が存在せず mock を直接描画している**。

- Overview: `frontend/src/routes/[org]/[project]/+page.svelte:4,33,40` が `overviewMock`
  （`frontend/src/lib/mock/overview-mock.ts:112`）を `OverviewDashboard` に直渡し。`client.ts` に `getOverview` は無い（grep 0 件）。
- Matrix: `client.listDebts`（`frontend/src/lib/api/client.ts:311`）/ `getDebt`（`:317`）は TODO で
  `MOCK_DEBTS`（`frontend/src/lib/api/mock/debts.ts:5`）を `applyFilterSort`（`client.ts:291`）に通すだけ。
  `createRepaymentPr` / `dismissDebt` / `assignDebt`（`client.ts:331,336,341`）は `ComingSoonError` スタブ。

本 issue は、Issue 028（`code_debts`）/ 029（`file_kc`）/ 030（`knowledge_debts` / `assigned_developers`）が
**検知・算出して永続化した行を、api 層が集計 / 配信 / 部分更新する読み取り・アクション API** を新設する。
重い検知 / 算出は一切持たず、`projects.py`（`backend/api/app/api/v1/projects.py:18-169`）の
`/orgs/{slug}/projects/{project_slug}/...` 配下に揃え、`OrgScope` 認可・snake_case 配信
（素の `BaseModel`、`stack.py` の `TechStackOut` パターン `backend/api/app/api/v1/stack.py:57-97`）に従う。

> 本 issue の責務は **集計 / 配信 / 部分更新（PATCH）まで**。検知 / 算出ロジック（028-030）・返済 PR 生成
> （`createRepaymentPr`、Issue 033）・trend の週次スナップショット蓄積の定期化（Issue 035 / 037）は **対象外**。
> 既存の検知結果が無い場合の挙動（404 / 空配列）を本 issue で明示する。

## 背景・目的

### 現状（フロントだけ・配信ゼロ）

- **Overview**: `overviewSchema`（`schemas.ts:202-208`）= `{ org, generated_at, files: fileDebtSchema[],
  trend: debtTrendPointSchema[], activity: weeklyActivitySchema }` が契約として確定。`fileDebtSchema`
  （`:180-187`）は `path` / `language` / `code_debt_score` / `knowledge_coverage` / `business_impact` / `priority`。
  描画は `overviewMock`（`overview-mock.ts:112`、`org:"demo"`、files 31 件、trend 4 週、activity 12/9/23/17）直読み。
- **Matrix**: `debtItemSchema = discriminatedUnion("kind", [codeDebtSchema, knowledgeDebtSchema])`（`schemas.ts:270`）、
  `debtListSchema = { debts, total }`（`:271-274`）。フィルタ（`DebtFilter` = `kind[]/severity[]/agent[]/status[]`、
  `client.ts:281`）・ソート（`DebtSort` = `key:"severity"|"detected_at"|"estimated_repay_hours", dir`、`:287`）は
  `applyFilterSort`（`:291-309`）と `SEVERITY_RANK`（`:289`、`critical:3/high:2/medium:1/low:0`）でクライアント側絞り込み。
- バックエンドには Overview 集計エンドポイントも `GET .../debts` 配信もアクション（PATCH）も無い。
  検知結果テーブル（`code_debts` / `knowledge_debts` / `assigned_developers` / `file_kc`）は 028-030 が新設する。

### 製品セマンティクス（出所）

独立した仕様書はリポジトリに存在せず、`docs/issue/007-overview-debt-matrix-dashboard.md` /
`docs/issue/008-matrix-debt-registry-drilldown.md` と `schemas.ts` を契約の正とする。

- **二軸負債モデル（007 §2.3）:** 縦 = コード品質（`code_debt_score` 低 = clean）、横 = チーム理解度
  KC（`knowledge_coverage` 高 = 皆理解）。`priority = code_debt × knowledge_debt × business_impact`
  （`schemas.ts:186`、`docs/issue/007-overview-debt-matrix-dashboard.md:165`）。`knowledge_debt = 1 - knowledge_coverage`。
- **priority 近似（008 §3）:** `business_impact` 未取得フェーズは二軸座標バンドで `derivePriority(code, 1-know)`
  近似（Issue 028 が `code_debts.priority` に派生保存。本 issue は保存値を配信、または join 時に算出）。
- **severity 量子化（008 §7.1, `:180`）:** float→4 段 enum。しきい値は 028/030 で確定済み
  （`>=0.75 critical / 0.50–0.75 high / 0.25–0.50 medium / <0.25 low`）。本 issue は永続化済み enum をそのまま配信。
- **今週の活動（007 §6.1）:** `weeklyActivitySchema`（`schemas.ts:195-200`）= `code_agent_prs` / `code_agent_merged`
  （Code Agent）/ `knowledge_agent_quizzes` / `knowledge_agent_passed`（Knowledge Agent）。
- **担当者の理解者 / 形式レビュー区別（008 §5.5, `:308-311`）:** `certified_via` + `coverage` から判定。
  配信時に `assigned_developers` を debt へ join する（生成は 029/030）。

### 設計方針

api は **集計 / 配信 / 部分更新** に徹し、検知 / 算出（028-030）の重い処理は持たない。レスポンスは schemas.ts に
合わせ **snake_case 維持**（`stack.py` の `TechStackOut` のように素の `BaseModel` を使い、`SharedBaseModel` の
camelCase `by_alias` は使わない）。フィルタ / ソートはフロントの `applyFilterSort` / `SEVERITY_RANK`
（`client.ts:289-309`）を **DB クエリ（`WHERE` / `ORDER BY` + severity ランクの `CASE`）で踏襲** する。

### ルート粒度の解決（org スコープ契約 vs project 実ルート）

`overviewSchema.org`（`schemas.ts:203`）と 007 想定 API `GET /api/v1/orgs/{org}/overview`
（`docs/issue/007-overview-debt-matrix-dashboard.md:199`）は **org 単位** を示唆するが、実フロントルートは
**project 単位**（`frontend/src/routes/[org]/[project]/+page.svelte`、`page.params.org` / `project`）であり、
検知データは原則プロジェクト単位（1 project = 1 repo）。`client.listDebts` も `orgSlug` 引数のみで mock は
`repo:"demo"` 固定。

**本 issue の決定:** 実ルートと検知データの粒度に合わせ、**すべて project スコープ**
（`/orgs/{slug}/projects/{project_slug}/...`）で実装する。`overviewSchema.org` フィールドは
**配信時に当該 project の `org.slug`（または org 名）を詰める**（契約のフィールド名は変えず値を org 識別子にする）。
org 横断集計の親ルートは本 issue では作らない（必要になれば将来 issue）。この判断は「対象外・保留」に明記する。

## 前提 issue（depends_on）

- **Issue 028** `docs/issue/028-backend-code-debt-detection-pipeline.md` — `code_debts` ORM
  （`project_id` / `file_path` / `type` / `severity` / `status` / `code_debt_score` / `knowledge_coverage` /
  `ai_generation_prob` / `estimated_repay_hours` / `priority` / `metrics`）と severity 量子化・`derivePriority`。
  本 issue は `GET .../debts`（code 行）と Overview `files` の `code_debt_score` をここから読む。
- **Issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc`（KC(file,dev) / KC(file) /
  `certified_via` / `mastery`）。Overview `files.knowledge_coverage` と debt の `knowledge_coverage` /
  `assigned_developers.coverage` の供給元。
- **Issue 030** `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — `knowledge_debts`
  （`reason` / `status:open/in_progress/resolved`、`related_pr` 無し）と `assigned_developers`
  （`debt_kind` + `debt_id` 判別カラム、`github_handle` / `coverage` / `certified_via`）。本 issue は
  `GET .../debts`（knowledge 行）と詳細 join をここから読む。

> 028/029/030 が確定するまで、各テーブルの具体カラム名（`code_debts` / `knowledge_debts` /
> `assigned_developers` / `file_kc`）は仮であり、最終形に合わせて集計クエリを整合させる（捏造しない）。
> `trend`（`debt_trend_point`）と `weekly_activity` の週次スナップショット蓄積の **定期化** は Issue 035/037
> が所有。本 issue は **集計クエリ + 配信** のみで、スナップショットが無い期間は空配列 / ゼロ埋めで返す。

## データモデル（新規 / 変更）

本 issue は **配信が主目的** であり、028-030 が作る検知テーブルを読む。新設するのは Overview の `trend` /
`activity` を保存する軽量テーブルのみ（集計の素データが他ドメインに無いため）。新規 ORM は **shared**
（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）に置き、Alembic は **api が所有**
（`backend/api/app/alembic/versions/`、連番は 028-030 の後続。雛形 `0003_add_tech_stacks.py` /
`0005_add_jobs.py`、`base.py` の naming convention）。id は `uuid.uuid4` default・`DateTime(timezone=True)`
（`backend/shared/shared/models/tech_stack.py:19-45` 踏襲）。

### 新規: `debt_trend_point`（`backend/shared/shared/models/debt_trend_point.py`）

`debtTrendPointSchema`（`schemas.ts:189-193`）= 週次スナップショット。`overviewMock.trend`（`overview-mock.ts:116-121`）に対応。

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`uuid4`、PK） | |
| `project_id` | `uuid.UUID`（FK → `projects.id`） | プロジェクト単位スコープ |
| `week` | `str` | `debtTrendPointSchema.week`（ISO 週 or ラベル `"今週"` 等、`schemas.ts:190`） |
| `code_debt_score` | `float`（0..1） | `schemas.ts:191`。当該週の集計値 |
| `knowledge_coverage` | `float`（0..1） | `schemas.ts:192`。当該週の集計 KC |
| `created_at` | `datetime`（tz aware） | スナップショット記録時刻 |

> `(project_id, week)` にユニーク制約を張る。**書き込み（週次スナップショットの生成）は Issue 037**
> （Cloud Functions / Pub-Sub の定期スキャンが `analysis_run` 時系列から生成）が所有。本 issue は **読み取りのみ**。
> 行が無い期間は `trend: []` で返す（フロントは空グラフで成立）。

### `weekly_activity` の扱い（動的集計）

`weeklyActivitySchema`（`schemas.ts:195-200`）は専用テーブルを作らず、**集計時に他ドメインの実テーブルから動的集計**する：

- `code_agent_prs` / `code_agent_merged`: `code_debts.related_pr` / `status=in_pr` 等の集計（028 の `code_debts`）。
- `knowledge_agent_quizzes` / `knowledge_agent_passed`: quiz セッション / 合格集計（**Issue 034** の `quiz_session`）。

> **未実装ドメインはゼロ埋め**で返す（034 未完なら `knowledge_agent_quizzes=0` 等）。週次の集計窓
> （直近 7 日 / ISO 週）の定義は本 issue で確定する。重い時系列の蓄積（trend）は 037 に委譲し、activity は
> 配信時のオンデマンド集計に留める（MVP）。

### 既存テーブルの変更

なし（028-030 が `code_debts` / `knowledge_debts` / `assigned_developers` / `file_kc` を所有。本 issue は読むだけ）。

## API（`/api/v1/...`）

すべて `projects.py` の `/orgs/{slug}/projects/{project_slug}/...` 配下に置き、`OrgScope`
（`backend/api/app/api/deps.py:64`、org member 認可）で保護する。レスポンスは **snake_case の素の `BaseModel`**
（`stack.py` `TechStackOut` パターン `:57-97`）。新ルーター（例 `api/v1/debts.py` + `api/v1/overview.py`、
または統合 `api/v1/insights.py`）を `backend/api/app/api/v1/router.py:13-20` に `include_router`（`projects_router` の隣）。

> **Annotated DI param 順序を変更しない**（CLAUDE.md「`Annotated[T, Depends(f)]` deps の宣言順序を変えない」。
> 順序変更は pytest teardown 中の DROP TABLE デッドロックを誘発）。`project_slug` 解決は `ProjectServiceDep.get_by_slug`
> （`backend/api/app/services/project.py`、`projects.py:64` 参照）で行い、集計は `project.id` でスコープする。

### (A) Overview 集計

#### `GET /api/v1/orgs/{slug}/projects/{project_slug}/overview` → `overviewSchema` 形

- レスポンス（新規 `OverviewOut`、snake_case）: `{ org, generated_at, files: list[FileDebtOut], trend:
  list[DebtTrendPointOut], activity: WeeklyActivityOut }`。`overviewSchema`（`schemas.ts:202-208`）に厳密一致。
- `org`: 当該 project の `org.slug`（ルート粒度の解決どおり、契約フィールド名は維持）。
- `generated_at`: 集計実行時刻（`z.iso.datetime({offset:true})`、`schemas.ts:204`。tz aware ISO）。
- `files` (`fileDebtSchema`, `schemas.ts:180-187`): 1 ファイル = 1 点。`code_debt_score` / `priority` は 028
  `code_debts`、`knowledge_coverage` は 029 `file_kc`、`language` は 026 `repo_file`（または `code_debts`）から
  ファイル単位で join 集計。`business_impact` は 028 注記どおり未取得フェーズは固定値（例 0.5）で埋める
  （「対象外・保留」に明記）。
- `trend` (`debtTrendPointSchema`): `debt_trend_point`（本 issue 新設）を `project_id` でスコープし `week` 昇順。無ければ `[]`。
- `activity` (`weeklyActivitySchema`): `code_debts` / quiz から動的集計（未実装ドメインはゼロ埋め）。
- 検知データが 1 件も無い場合: `files: []` / `trend: []` / `activity` ゼロ埋めの **200**（フロントは Coming Soon
  オーバーレイを維持できる）。404 にはしない（`overviewSchema.observed` 相当のフラグは契約に無いため空で返す）。

### (B) Matrix 負債レジストリ

#### `GET /api/v1/orgs/{slug}/projects/{project_slug}/debts` → `debtListSchema` 形

- レスポンス（新規 `DebtListOut`、snake_case）: `{ debts: list[DebtItemOut], total: int }`。`debtListSchema`
  （`schemas.ts:271-274`）に一致。`DebtItemOut` は `codeDebtSchema`（`:230-249`）/ `knowledgeDebtSchema`
  （`:251-268`）の合併で、`kind` 判別。`assigned_agent`（`"code_debt"` / `"knowledge_debt"`、固定リテラル
  `:247,266`）は配信時に付与（列にしない、028/030 注記）。
- code 行は `code_debts`（028）、knowledge 行は `knowledge_debts`（030）から取得し union。各 debt の
  `assigned_developers`（`assignedDeveloperSchema`、`:224-228`）を `assigned_developers`（030 新設、`debt_kind` +
  `debt_id` 判別）から join。
- クエリパラメータ（`DebtFilter` / `DebtSort`、`client.ts:281-287` を DB クエリで踏襲）:
  - `kind`（`code/knowledge` 複数）/ `severity`（`critical/high/medium/low` 複数）/ `agent`
    （`code_debt/knowledge_debt` 複数 = `assigned_agent`）/ `status`（複数）→ `WHERE ... IN (...)`。
  - `sort_key`（`severity/detected_at/estimated_repay_hours`）/ `sort_dir`（`asc/desc`）→ `ORDER BY`。
    `severity` ソートは `SEVERITY_RANK`（`client.ts:289`、`critical:3/high:2/medium:1/low:0`）を `CASE` 式で再現。
- `total` は **フィルタ適用後の件数**（フロント mock は `debts.length`、`client.ts:314`）。
- 検知結果が無い場合: `{ debts: [], total: 0 }` の 200。

#### `GET /api/v1/orgs/{slug}/projects/{project_slug}/debts/{debt_id}` → `debtItemSchema` 形

- 単一 debt を返す（`debtItemSchema` discriminatedUnion、`schemas.ts:270`）。`code_debts` / `knowledge_debts` を
  `debt_id` で引き、`assigned_developers` を join。`code_snippet`（`:242,261`）・`archaeology_notes`（code のみ `:241`）を含む。
- 404 = 該当 debt なし（`getDebt` の `throw new Error("負債が見つかりません")`、`client.ts:320` に対応）。

#### `PATCH /api/v1/orgs/{slug}/projects/{project_slug}/debts/{debt_id}` → `debtItemSchema` 形

- 部分更新（CLAUDE.md「更新は PATCH」）。リクエストボディ（新規 `DebtUpdate`、全フィールド optional）:
  - `status`: code は `open/in_pr/resolved/dismissed`（`:237`）、knowledge は `open/in_progress/resolved`
    （`:258`、`dismissed` 無し）。`dismissDebt`（`client.ts:336`）= `status="dismissed"`（code のみ許可）。
  - `assigned_developers`（または assign 用の `github_handle` + `certified_via` + `coverage`）: `assignDebt`
    （`client.ts:341`、`handle` 引数）に対応。`assigned_developers` 行を upsert。
- レスポンスは更新後の `debtItemSchema` 形（フロントが楽観更新に使える）。
- kind に応じた status 値の検証（knowledge に `dismissed` を弾く等）と 404 / 422 を返す。

> **返済 PR 生成（`createRepaymentPr`、`client.ts:331`）は本 issue の対象外**（Issue 033 が
> `POST .../debts/{debt_id}/repayment-pr` → `202 {job_id}` で実装）。本 issue では `ComingSoonError` スタブを残す。

### 認可

全エンドポイント `OrgScope`（org member、`deps.py:64`）。`PATCH`（dismiss / assign）を admin 限定にするかは
書込の影響度から **org member（read-write 相当）で可** とするが、`OrgAdminScope`（`deps.py:65`）に上げる選択肢も
明記する（設計判断）。**Annotated DI param 順序厳守**。

## パイプライン・非同期

**本 issue は同期の集計 / 配信 API のみで、新規パイプライン・JobType・enqueue は追加しない。**
重い検知 / 算出は前提 issue（028-030）の既存パイプラインが担い、本 issue はその永続化済み行を読むだけである
（`stack.py::get_stack` `:146-167` のような同期 GET と同型）。

- **trend の週次スナップショット蓄積の定期化**は CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・
  Pub/Sub）」に従い **Issue 037** が `analysis_run` 時系列から `debt_trend_point` を生成する。本 issue は読むのみ。
- **activity** は配信時のオンデマンド集計（`code_debts` / quiz テーブルへの集計クエリ）に留める。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `models/debt_trend_point.py` に `DebtTrendPoint` ORM を新設（雛形 `tech_stack.py:19-45`。上表の列・
      `(project_id, week)` ユニーク制約）。
- [ ] `models/__init__.py:3-6` に `DebtTrendPoint` を re-export 追加（import 順 app→shared 規約）。
- [ ] `enums.py` の負債系 StrEnum（`Severity` / `CodeDebtType` / `DebtStatus` / `DebtPriority` /
      `KnowledgeDebtReason` / `DebtKind`、028/030 が新設）を配信整形・フィルタ検証に再利用（重複定義しない）。

### api（`backend/api/app/`）

- [ ] `alembic/versions/00NN_add_debt_trend_points.py` を新設（028-030 の後続連番。雛形
      `0003_add_tech_stacks.py` / `0005_add_jobs.py`、`base.py` naming convention。`(project_id, week)` ユニーク）。
- [ ] `schemas/overview.py` / `schemas/debt.py`（または統合）に snake_case の `OverviewOut` / `FileDebtOut` /
      `DebtTrendPointOut` / `WeeklyActivityOut` / `DebtListOut` / `DebtItemOut` / `AssignedDeveloperOut` /
      `DebtUpdate` を定義（素の `BaseModel`、`stack.py:36-65` の `TechStackOut` パターン。schemas.ts に厳密一致）。
- [ ] `api/v1/overview.py` に `GET .../overview` を実装（`OrgScope` `deps.py:64`、`ProjectServiceDep.get_by_slug`
      で project 解決、`code_debts`/`file_kc`/`debt_trend_point` を `project.id` で集計、activity 動的集計、
      Annotated DI param 順序厳守）。
- [ ] `api/v1/debts.py` に `GET .../debts`（フィルタ/ソートを DB クエリ化 = `applyFilterSort`/`SEVERITY_RANK`
      `client.ts:289-309` を `WHERE`/`ORDER BY`/`CASE` で踏襲）/ `GET .../debts/{debt_id}` /
      `PATCH .../debts/{debt_id}`（status=dismissed / assigned 更新、kind 別 status 検証）を実装。
- [ ] `api/v1/router.py:13-20` に新ルーターを `include_router`（`projects_router` の隣）。
- [ ] `assigned_developers`（030）を debt へ join するクエリヘルパ（`(debt_kind, debt_id)` index 前提、030 注記）。

### service（`backend/service/service/`）

- [ ] 変更なし（本 issue は同期配信のみ。検知 / 算出パイプラインは 028-030 が所有）。

### frontend（`frontend/src/`）

- [ ] `client.ts` に `getOverview(orgSlug, projectSlug)` を追加（`overviewSchema.parse` で検証。`listProjects`
      `client.ts:154` 等の `apiFetch` 規約に合わせる）。
- [ ] `client.listDebts`（`client.ts:311`）の TODO を実 API（`GET .../debts`）へ差し替え（フィルタ/ソートは
      クエリパラメータでサーバへ委譲、または当面サーバ取得 + 既存 `applyFilterSort` 併用）。`getDebt`（`:317`）も
      `GET .../debts/{debt_id}` へ差し替え。引数を project スコープ（`orgSlug, projectSlug`）に合わせて拡張。
- [ ] `dismissDebt`（`client.ts:336`）/ `assignDebt`（`:341`）の `ComingSoonError` スタブを `PATCH .../debts/{debt_id}`
      実装へ差し替え（`createRepaymentPr` `:331` は Issue 033 まで据え置き）。
- [ ] `frontend/src/routes/[org]/[project]/+page.svelte:4,33,40` の `overviewMock` 直読みを `getOverview` 呼び出しへ
      差し替え（`+page.ts` ローダーまたは `onMount`、ssr=false）。
- [ ] schemas.ts は既存のまま流用（`overviewSchema` / `debtListSchema` / `debtItemSchema` は変更不要）。

### infra

- [ ] trend 週次スナップショットの定期生成（Cloud Functions / Pub-Sub）は **Issue 037** に委譲（本 issue では追加しない）。

### test

- [ ] api（`backend/api/tests/`）: `GET .../overview` が `overviewSchema` 形（snake_case）を返し、`org` が project の
      org slug、検知データ無し時に `files:[]`/`trend:[]`/`activity` ゼロ埋めで 200 を返すこと。
- [ ] api: `GET .../debts` がフィルタ（`kind`/`severity`/`agent`/`status` の `IN`）・ソート（`severity` の `CASE`
      ランク・`detected_at`・`estimated_repay_hours`、`asc/desc`）を DB クエリで正しく適用し、`total` が
      フィルタ後件数になること。`SEVERITY_RANK`（`client.ts:289`）と一致する順序。
- [ ] api: `GET .../debts/{debt_id}` が `debtItemSchema`（code / knowledge 両 kind）の形で `assigned_developers`
      join 込みで返し、未存在で 404。
- [ ] api: `PATCH .../debts/{debt_id}` が `status=dismissed`（code）/ `assigned` 更新を部分適用し、knowledge への
      `dismissed` を 422 で弾くこと。`OrgScope` 認可（非メンバー 403）。
- [ ] frontend: `client.getOverview` / `listDebts` / `getDebt`（API モック）のユニットテストと、
      `+page.svelte` が実 API データで Overview を描画する `.svelte.spec.ts`（browser-mode）。

## 完了条件

- `GET .../overview` が `overviewSchema` に厳密一致する snake_case レスポンスを返し、`files`（028 `code_debts` +
  029 `file_kc` 集計）/ `trend`（`debt_trend_point`）/ `activity`（`code_debts` + quiz 動的集計・未実装ドメインゼロ埋め）が
  project スコープで揃う。検知データ無し時も 200（空）で返る。
- `GET .../debts` が `debtListSchema` 形でフィルタ / ソートを **DB クエリ**で適用し、`applyFilterSort` /
  `SEVERITY_RANK`（`client.ts:289-309`）と同じ結果を返す。`GET .../debts/{debt_id}` が `debtItemSchema`
  （code / knowledge）を `assigned_developers` join 込みで返す。
- `PATCH .../debts/{debt_id}` が `status=dismissed`（code）/ assign を部分更新（PATCH 規約）し、kind 別 status を検証する。
- フロントの `+page.svelte` の `overviewMock` 直読みと `client.listDebts` / `getDebt` / `dismissDebt` / `assignDebt`
  の mock / スタブが実 API に差し替わる（`createRepaymentPr` は Issue 033 まで据え置き）。
- 全レスポンスが `OrgScope`（org member）認可下にあり、Annotated DI param 順序が保持されている。
- バックエンド: `cd backend && uv run ruff check shared/shared api/app service/service && uv run ruff format --check shared/shared api/app service/service`
  / `uv run ty check shared/shared api/app service/service` / `uv run --directory shared pytest` / `--directory api pytest` / `--directory service pytest` が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語, Keep a Changelog）に `Added`（Overview 集計 API / 負債レジストリ配信・PATCH API /
  `debt_trend_point` テーブル）を追記。

## 対象外・保留

- **検知 / 算出ロジック**: `code_debts`（028）/ `file_kc`（029）/ `knowledge_debts` / `assigned_developers`（030）の
  生成は前提 issue が所有。本 issue は読むだけ。
- **返済 PR 生成**（`POST .../debts/{debt_id}/repayment-pr`、`createRepaymentPr` `client.ts:331` のスタブ解消）— **Issue 033**。
- **trend の週次スナップショット蓄積の定期化**（`debt_trend_point` の書き込み、Cloud Functions / Pub-Sub）— **Issue 037**。
  本 issue は `debt_trend_point` テーブルの新設と **読み取り配信** までで、書き込みは持たない。
- **`weekly_activity` の quiz 側集計**（`knowledge_agent_quizzes` / `knowledge_agent_passed`）は Issue 034
  の `quiz_session` テーブル成立後に実値化。未実装の間はゼロ埋め。
- **`business_impact` の実取得**（doc 008 §3 注記）— 将来。本 issue では固定値で埋める。
- **`priority` の派生保存 vs 配信時算出**の最終一貫性: 028 が `code_debts.priority` を派生保存する前提で、本 issue は
  保存値を配信する（保存値が古い場合のリスクは将来吸収）。
- **org 横断集計の親ルート**（`GET /api/v1/orgs/{org}/overview`）: 本 issue は project スコープに統一し作らない。
  必要になれば将来 issue。
- **pgvector による重複クラスタ表示等**の高度化 — 将来（拡張有効化は Issue 026）。

## 参考

- 関連 issue
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 同期 GET 配信（`get_stack`）と snake_case 素 `BaseModel`（`TechStackOut`）の雛形
  - `docs/issue/028-backend-code-debt-detection-pipeline.md` — `code_debts` / severity 量子化 / `derivePriority`（前提）
  - `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc`（KC 供給元・前提）
  - `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — `knowledge_debts` / `assigned_developers`（前提）
  - `docs/issue/007-overview-debt-matrix-dashboard.md` — Overview 二軸モデル（§2.3）/ `overviewSchema`（`:199` 想定 API）
  - `docs/issue/008-matrix-debt-registry-drilldown.md` — `debtItemSchema` 製品セマンティクス（§3 priority / §5.5 理解者判定 `:308-311` / §7.1 severity `:180`）
  - `docs/issue/033-...`（返済 PR）/ `034-...`（quiz、activity 集計連携）/ `037-...`（定期スキャン・trend 蓄積）
- 契約（フロント）
  - `frontend/src/lib/api/schemas.ts:180-214`（`fileDebtSchema`/`debtTrendPointSchema`/`weeklyActivitySchema`/`overviewSchema`）
  - `frontend/src/lib/api/schemas.ts:220-283`（`severitySchema`/`certifiedViaSchema`/`assignedDeveloperSchema`/`codeDebtSchema`/`knowledgeDebtSchema`/`debtItemSchema`/`debtListSchema`）
  - `frontend/src/lib/mock/overview-mock.ts:112-128`（`overviewMock`）/ `frontend/src/lib/api/mock/debts.ts:5`（`MOCK_DEBTS`）
  - `frontend/src/lib/api/client.ts:281-346`（`DebtFilter`/`DebtSort`/`SEVERITY_RANK`/`applyFilterSort`/`listDebts`/`getDebt`/`dismissDebt`/`assignDebt`/`createRepaymentPr`）/ `:154`（`listProjects` の `apiFetch` 規約）
  - `frontend/src/routes/[org]/[project]/+page.svelte:4,33,40`（`overviewMock` 直読み・差し替え対象）
- 既存 backend（雛形・流用）
  - `backend/api/app/api/v1/stack.py:57-97`（`TechStackOut` 素 `BaseModel` snake_case）/ `:146-167`（同期 GET 配信 `get_stack`）
  - `backend/api/app/api/v1/projects.py:18-169`（`/orgs/{slug}/projects/{project_slug}` ルート形・`OrgScope`/`OrgAdminScope`・PATCH 例 `:115-142`）
  - `backend/api/app/api/deps.py:64-66`（`OrgScope`/`OrgAdminScope`）/ `backend/api/app/services/project.py`（`ProjectServiceDep.get_by_slug`）
  - `backend/api/app/api/v1/router.py:13-20`（ルーター登録）/ `backend/api/app/api/v1/jobs.py`（既存ジョブ配信）
  - `backend/shared/shared/models/tech_stack.py:19-45`（ORM 雛形）/ `models/__init__.py:3-6`（re-export 順）
  - `backend/api/app/alembic/versions/0003_add_tech_stacks.py` / `0005_add_jobs.py`（マイグレーション雛形・連番は 028-030 の後続）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — snake_case 配信（素 `BaseModel`）/ Annotated DI param 順序厳守 /
    `models/__init__.py` import 順（app→shared）/ `router.py` ルーター登録 / PATCH 部分更新 /
    ゲート（`uv run ruff`/`ty`/`pytest`、`bun run check`/`lint`/`test:unit`）/ `CHANGELOG.md`（日本語）
