# 解析データ基盤を新設する（analysis_run / repo_file 共有テーブル + JobType 拡張規約 + pgvector 拡張）

## 概要

Overview 二軸ダッシュボード・負債レジストリ（Matrix）・Galaxy 個人 KC マップ・Quiz・Agents
といった各 Map ドメインは、いずれも「あるリポジトリのある時点を解析した結果」を土台に描画される。
しかし現状のバックエンドには、その**解析結果を載せる共有の器**が存在しない
（既存テーブルは `users` / `oauth_account` / `orgs` / `projects` / `refresh_token`（api）と
`jobs` / `tech_stacks`（shared）のみ。Alembic は 0001〜0005）。
各ドメインのフロントは `frontend/src/lib/mock/overview-mock.ts` / `frontend/src/lib/api/mock/debts.ts` /
`frontend/src/lib/mocks/galaxy.ts` 等のモックを直接描画している。

本 issue は、後続の全解析ドメイン（027〜037）が共通して参照する**最小の土台**だけを確定する。
個別の解析ロジック・スコア算出・配信 API・KC/負債の式は **本 issue では実装しない**（後続 issue が所有）。
具体的には次の 4 点に絞る：

1. `shared/shared/models/` に **`analysis_run`**（= リポジトリスナップショット軸）と
   **`repo_file`**（= File 同一性アンカー）の 2 つの共有 ORM を新設し、`models/__init__.py` に再 export する。
2. api 所有の **Alembic 0006** で上記 2 テーブルを作成し、併せて
   **`CREATE EXTENSION IF NOT EXISTS vector`**（pgvector）を実行する（後続の埋め込み類似検索の前提配線のみ。
   本 issue では `vector` 列は持たない）。
3. `shared/shared/enums.py` の **`JobType`** に後続解析 pipeline 値を追加する**命名規約**を確立する
   （本 issue では値の追加はしない。規約のドキュメント化のみ）。
4. **File 同一性 / 開発者識別子（`users.id` か GitHub login か） / run スコープの正規化方針**を
   **ADR** として `docs/adr/` に記す（独立仕様書が存在しないため、製品判断を明示）。

雛形は 018 でフォーマットが固まった `shared/shared/models/tech_stack.py`・
`api/app/alembic/versions/0003_add_tech_stacks.py`・`0005_add_jobs.py` をそのまま踏襲する。

## 背景・目的

### 現状（解析結果の器が無い）

- 非同期基盤は 016/018 で完成している：`shared` に `Job`（`shared/shared/models/job.py`）と
  `JobType`（`shared/shared/enums.py:11`）、api の `enqueue_job`、service の `/tasks/{pipeline}`、
  `shared.worker.run_task` の冪等書き戻し、`service/service/registry.py` の `(Request, Result, process)`
  三つ組登録（`service/service/registry.py:15`）。これらは「重い解析を service に載せる」ための配線として
  そのまま使える。
- しかし `Job.result_data`（JSONB）だけでは、ファイル単位・開発者単位の解析結果を**横断クエリ**できない。
  Overview の散布図（`fileDebtSchema`）・Matrix の一覧（`debtItemSchema`）・Galaxy の星系
  （`starSystemSchema` / `wormholeSchema`）は、いずれも「project × commit × file」を join キーにした
  集計を要求するため、正規化テーブルが要る。
- 後続の各解析 issue（028 コード負債 / 029 KC / 030 知識負債 / 032 Galaxy 等）は、それぞれ独自に
  `file_path` / `run` / `dev_id` を定義しがちで、**join 不能・二重定義**になるリスクが高い
  （関連ドメインの risks 欄でも指摘済み）。これを防ぐため、**全ドメインが共有する 2 軸**
  （run = いつのスナップショットか / file = どのファイルか）と**識別子の正規形**を本 issue で固定する。

### 目的

1. 「どの時点のリポジトリを解析したか」を表す **`analysis_run`**（project_id / commit_sha / branch / kind /
   job_id / status / created_at）を確定する。trend（週次推移）はこの run の時系列から導出する設計の起点。
2. 「どのファイルか」を表す **`repo_file`**（run_id / path / language / loc、`(run_id, path)` 一意）を確定する。
   後続の `file_debt` / `file_kc` / `dependency`（027〜032 が新設）はすべてこの `repo_file` を File 同一性の
   アンカーとして参照する。
3. pgvector を migration レベルで有効化し、重複検知・概念マッピングの埋め込み類似検索を将来配線できる状態にする
   （現状 `compose.yml` / `compose.prod.yml` は `pgvector/pgvector:pg17` を使うのみで、`CREATE EXTENSION vector`
   も `vector` 列も Python コードもゼロ＝「箱は有るが未配線」）。
4. `JobType` 追加の命名規約（lowercase snake_case = queue/task path 名）と、File 同一性・dev 識別子・run スコープの
   正規化方針を文書（コメント + ADR）として残し、後続 issue が迷わず join できる契約を確定する。

### 前提 issue（depends_on）

- **Issue 016** `docs/issue/016-async-task-queue-cloud-tasks.md` — `shared` の `Job` モデル・`JobType` enum・
  `enqueue_job` / `TaskDispatcher` / `/tasks/{pipeline}` / `shared.worker.run_task` の基盤。本 issue の
  `analysis_run.job_id`（FK → `jobs.id`）と JobType 追加規約はこの上に乗る。
- **Issue 018** `docs/issue/018-stack-analysis-async-job-on-service.md` — 共有 ORM（`shared/shared/models/tech_stack.py`）・
  Alembic 雛形（api 所有、`0003` / `0005`）・`models/__init__.py` の import 順（app→shared）・
  pipeline 三つ組登録（`service/service/registry.py`）の**様式の正典**。本 issue の新規テーブルはこの様式に倣う。

> 本 issue は新しい pipeline を**登録しない**。`analysis_run` の `kind` 値や `JobType` の具体値の追加は、
> 各解析 issue（028 以降）が自分のドメインで行う。本 issue はその**置き場と命名規約**を用意するだけである。

### 独自性（他 issue との差分）

028〜037 が「個別ドメインの解析・配信」であるのに対し、本 issue は唯一の **foundation（土台）issue** であり、
(a) どのドメインにも属さない共有 2 テーブルと識別子正規形を確定する、(b) pgvector を migration で有効化して
将来の類似検索の前提だけ作る、(c) コードを増やさず**規約（命名規約・ADR）を確定する**、という点で性質が異なる。
個別の解析ロジック・スコア式・配信 API・KC/負債算出は一切含まない。

## データモデル

新規 2 テーブルはいずれも **`shared`**（`shared/shared/models/`）に置く。理由は 018 の `TechStack` と同じく、
api が読み（集計・配信）service が書く（解析 DML）の双方から `from shared.models import AnalysisRun, RepoFile`
で参照されるため。`shared` の依存は `pydantic>=2` + `sqlmodel` のみを維持する（重い依存は載せない）。
id は `shared` を軽量に保つため `tech_stack.py` / `job.py` と同じく **`uuid.uuid4` default**
（api 側の `uuid7_pk()` は使わない）。タイムスタンプは **`DateTime(timezone=True)`**。

Alembic マイグレーションと DB エンジン/セッション生成は 018 どおり **api が所有**
（`api/app/alembic/` / `api/app/core/db.py`）。service はマイグレーションを持たず、薄いセッションで DML するのみ。

### 新規テーブル 1: `analysis_run`（リポジトリスナップショット軸）

「どの project の、どの commit を、どの解析種別で解析したか」のヘッダ。1 回の解析実行 = 1 行。
後続の `repo_file` / `file_debt` / `file_kc` / `dependency` はこの run を時間軸の親に持つ。

| 列 | 型 | 説明 |
|---|---|---|
| `id` | `uuid` PK（`uuid4` default） | `tech_stack.py:28` 同形 |
| `project_id` | `uuid` FK → `projects.id`、index、not null | 解析対象 project（`api/app/models/project.py:13`。1 project = 1 repo） |
| `commit_sha` | `str`、index、not null | 解析した時点の commit。冪等・trend スナップショットのキー（037 が同 `commit_sha` の重複 run 抑止に使う） |
| `branch` | `str`、not null、default `"main"` | 解析対象ブランチ（`projects.default_branch` 既定 `main` に整合） |
| `kind` | `str`、index、not null | 解析種別。値は `JobType` 値に揃える（lowercase snake_case。後続 issue が `code_debt_detection` 等を入れる） |
| `job_id` | `uuid` FK → `jobs.id`、nullable、index | この run を生成した非同期 Job（`shared/shared/models/job.py:18`）。手動/定期どちらの run か追える |
| `status` | `str`、index、not null | run のライフサイクル。値は `JobStatus`（`shared/shared/enums.py:19`、UPPERCASE）に揃える |
| `created_at` | `datetime`（tz aware）、`server_default=now()` | `0005_add_jobs.py:32` と同形 |

> `project_id` への FK は 018 の `Job.project_id`（FK 無しの nullable）とは異なり、**実 FK を張る**
> （`projects` テーブルは 0004 で既に存在する。`analysis_run` は project スコープが本質のため）。
> `kind` / `status` を専用 enum 列にせず String にするのは、`Job.job_type` / `Job.status` が
> 「String 保存・native PG enum を作らない」プロジェクト規約（`shared/shared/models/job.py:29` のコメント）に
> 倣うため。後続 issue が新 `kind` を増やしても migration 不要にする狙い。

### 新規テーブル 2: `repo_file`（File 同一性アンカー）

`analysis_run` × ファイル。1 run の中で観測された 1 ファイル = 1 行。
後続の `file_debt`（028）/ `file_kc`（029）/ `dependency`（029, from/to は path）は、すべてこの `repo_file`
（または `(run_id, path)`）を File の同一性キーとして参照する。

| 列 | 型 | 説明 |
|---|---|---|
| `id` | `uuid` PK（`uuid4` default） | |
| `run_id` | `uuid` FK → `analysis_run.id`、index、not null | 所属する解析 run |
| `path` | `str`、not null | リポジトリルートからの相対パス（GitHub tree の path。`github_git_client.py:43` `TreeItem` 由来） |
| `language` | `str`、nullable | 主要言語（`fileDebtSchema.language` / `fileMasterySchema` の素材）。判定不能は null |
| `loc` | `int`、nullable | 行数（lines of code）。複雑度・規模指標の素材 |
| `created_at` | `datetime`（tz aware）、`server_default=now()` | |

- **一意制約:** `UniqueConstraint("run_id", "path", name="uq_repo_files_run_id_path")`
  （`tech_stack.py:26` の `uq_tech_stacks_owner_repo` と同パターン）。1 run 内でパスは一意。
- **File 同一性の方針（ADR で確定）:** File はまず `(run_id, path)` で同定する。リポジトリ横断・run 横断の
  「同じファイル」は path の一致で近似する（rename 追跡は本 issue の責務外。git rename 追跡が要るなら 027 の
  blame/履歴拡張で扱う）。`repo_file.path` を File 同一性の唯一の安定キーとする旨を ADR に明記する。

### pgvector 拡張の有効化（vector 列は本 issue では持たない）

- Alembic 0006 の `upgrade()` 冒頭で `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` を実行する。
  これは**重複検知・概念マッピングの埋め込み類似検索の前提配線のみ**で、本 issue では `vector` 型の列も
  `pgvector` python パッケージ依存も追加しない（実利用は将来 issue。037 の非責務欄でも将来扱いと明記）。
- 既存 image は `compose.yml` / `compose.prod.yml` が `pgvector/pgvector:pg17` を使用済みのため、拡張は作成可能。
- `naming convention` は `api/app/models/base.py:11` の `convention`（`ix/uq/ck/fk/pk`）を踏襲する
  （0006 の制約・index 名は `op.f(...)` で自動命名に揃える）。

### Alembic 0006（api 所有）

- 連番は `0005_add_jobs.py` の次＝**`0006`**。`down_revision = "0005"`、`revision = "0006"`。
- ファイル名は既存様式に倣い `api/app/alembic/versions/0006_add_analysis_runs_and_repo_files.py`。
- `upgrade()`:
  1. `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`
  2. `op.create_table("analysis_runs", ...)` — `analysis_run` モデル（`__tablename__ = "analysis_runs"`）。
     `ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_analysis_runs_project_id_projects"))` と
     `ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_analysis_runs_job_id_jobs"))`、
     index（`project_id` / `commit_sha` / `kind` / `status` / `job_id`）。`0004_add_projects.py:38` の FK 命名が参考。
  3. `op.create_table("repo_files", ...)` — `repo_file` モデル。
     `ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_repo_files_run_id_analysis_runs"))` と
     `UniqueConstraint("run_id", "path", name="uq_repo_files_run_id_path")`、`run_id` index。
- `downgrade()`: `repo_files` → `analysis_runs` の順で drop（FK の逆順）。pgvector 拡張の DROP は**行わない**
  （他で利用される可能性があり、`DROP EXTENSION` は破壊的なため downgrade では触らない旨をコメントで明記）。
- `models/__init__.py`（`shared/shared/models/__init__.py`）に `AnalysisRun` / `RepoFile` を追加し
  `from shared.models import AnalysisRun, RepoFile` を可能にする。併せて api の `app/models/__init__.py` でも
  shared の import 行（現 `from shared.models import Job, TechStack`、`app.models` の **後** に配置）に追記する
  ── これにより `app.models.base` が `SQLModel.metadata` を naming-convention 付きに差し替えた後で shared テーブルが
  読まれ、Alembic autogenerate / テストの `create_all` が新テーブルを拾う（`api/app/models/__init__.py` の
  既存コメントどおり import 順 app→shared を厳守）。

## API

**本 issue は API を追加しない。** 集計・配信エンドポイント（Overview / Matrix / Galaxy / Quiz / Learning /
Agents）と enqueue ルートは、すべて後続 issue（028〜036）が `projects.py` の
`/api/v1/orgs/{slug}/projects/{project_slug}/...` スコープ配下に追加する。

ただし後続 issue が本テーブルから集計して満たすべき**フロント契約（schemas.ts）**を、join の正として明示しておく
（本 issue はこの契約に直接は触れないが、`repo_file` / `analysis_run` がこれらの join 基盤になる）：

- `fileDebtSchema`（`frontend/src/lib/api/schemas.ts:180`）— `path` / `language` / `code_debt_score` /
  `knowledge_coverage` / `business_impact` / `priority`。`path` / `language` は `repo_file` 由来、スコア類は 028/029 が
  `repo_file` を親に持つ `file_debt` / `file_kc` から供給。
- `debtTrendPointSchema`（`schemas.ts:189`）— `week` / `code_debt_score` / `knowledge_coverage`。
  `analysis_run.commit_sha` + `created_at` の時系列スナップショットから 037 が導出。
- `debtItemSchema`（`schemas.ts:270`、discriminatedUnion）/ `starSystemSchema`・`wormholeSchema`（`schemas.ts:303`）—
  いずれも `file_path` / `repo` / from-to path を持ち、`repo_file.path` を File 同一性キーに join される。

レスポンスは 018 の `TechStackOut` パターン（素の `BaseModel` で snake_case 配信。`Job.result_data` の
camelCase とは別系統）を後続 issue が踏襲する。これも本 issue では実装しない。

## パイプライン・非同期

**本 issue は pipeline を追加・登録しない。** ただし後続 issue が `JobType` を増やすときの**規約を確定**する
（`shared/shared/enums.py:1` の docstring に既述の規約をこの issue で正式化・ドキュメント化）：

- **命名規約:** `JobType` の値は **lowercase snake_case**。値はそのまま queue / task path 名へ `_` → `-` 変換される
  （例 `code_debt_detection` → task path `code-debt-detection`）。`shared/shared/enums.py:11` の `JobType` に
  `ECHO` / `PING` / `STACK_ANALYSIS` が既存。後続 issue は同形で 1 値ずつ追加する。
- **追加手順（後続 issue 向けチェックリスト）:**
  1. `shared/shared/enums.py` の `JobType` に新値を追加（例 `CODE_DEBT_DETECTION = "code_debt_detection"`）。
  2. `shared/shared/schemas/<pipeline>.py` に `JobRequestBase` / `JobResultBase` を継承した Request/Result を定義
     （`shared/shared/schemas/stack_analysis.py:58` が雛形。GitHub アクセスは `GitHubRef`（`installation_id` のみ＝方式B））。
  3. `service/service/pipelines/<pipeline>.py` に `async def process(request, ctx: PipelineContext) -> Result`
     を実装（`service/service/pipelines/stack_analysis.py:361` が雛形。`ctx.session` で DML、`on_conflict_do_update`
     upsert は `stack_analysis.py:222` 参照）。
  4. `service/service/registry.py` の `PIPELINES` に `(Request, Result, process)` 三つ組を追記
     （`service/service/registry.py:15`）。
  5. api 側 enqueue ルートは `stack.py::analyze_stack`（202 + `JobEnqueuedOut`）をコピーして `job_type` を変えるだけ。
- `analysis_run.kind` / `analysis_run.status` の値は、それぞれ `JobType` 値 / `JobStatus` 値に揃える
  （文字列で保存。native PG enum は作らない）。

**定期スキャン**（Cloud Functions + Cloud Scheduler/Pub-Sub。CLAUDE.md「非同期ジョブ = Cloud Functions」）は
**037 の責務**であり本 issue では実装しない。本 issue は、037 が冪等な巡回 enqueue を組めるよう
`analysis_run.commit_sha`（同 commit の重複 run を抑止するキー）を用意するに留める。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `shared/shared/models/analysis_run.py` を新設し `AnalysisRun`（`__tablename__ = "analysis_runs"`）を定義する。
      `tech_stack.py`（`shared/shared/models/tech_stack.py:19`）の様式に倣い `uuid4` PK・`DateTime(timezone=True)`・
      String 保存の `kind` / `status`。列は上表（project_id FK / commit_sha / branch / kind / job_id FK / status / created_at）。
- [ ] `shared/shared/models/repo_file.py` を新設し `RepoFile`（`__tablename__ = "repo_files"`）を定義する。
      列は上表（run_id FK / path / language / loc / created_at）+ `UniqueConstraint("run_id", "path", name="uq_repo_files_run_id_path")`
      （`tech_stack.py:26` の UniqueConstraint パターン）。
- [ ] `shared/shared/models/__init__.py`（現 `from shared.models.job import Job` / `from shared.models.tech_stack import TechStack`、
      `shared/shared/models/__init__.py:3`）に `AnalysisRun` / `RepoFile` の import と `__all__` 追記。
- [ ] `shared/shared/enums.py` の docstring（`shared/shared/enums.py:1`）に JobType 命名規約（lowercase snake_case =
      queue/task path、`_`→`-` 変換）を正式記述する。`JobType` への値追加は本 issue では**行わない**
      （`shared/shared/enums.py:11` は `ECHO` / `PING` / `STACK_ANALYSIS` のまま）。

### api（`backend/api/app/`）

- [ ] `api/app/alembic/versions/0006_add_analysis_runs_and_repo_files.py` を新設する
      （`revision="0006"` / `down_revision="0005"`）。`upgrade()` で
      `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` → `analysis_runs` → `repo_files` を作成。
      FK・index・UniqueConstraint は `0004_add_projects.py:38` / `0003_add_tech_stacks.py:31` の命名様式
      （`op.f(...)`、`api/app/models/base.py:11` の convention）に揃える。`downgrade()` は FK 逆順 drop、
      pgvector 拡張は drop しない（コメント明記）。
- [ ] `api/app/models/__init__.py` の shared import 行（現 `from shared.models import Job, TechStack`、
      `app.models` 群の**後**＝import 順 app→shared）に `AnalysisRun` / `RepoFile` を追記し `__all__` を更新する。
- [ ] migration 適用後に `analysis_runs` / `repo_files` テーブルと `vector` 拡張が作成されることを確認する
      （`docker compose watch` 起動 → `uv run --directory api alembic upgrade head`、または pgAdmin
      `docker compose --profile tools up` で `\dx` 相当確認）。

### service（`backend/service/service/`）

- [ ] 本 issue では service コードの変更**なし**（pipeline 登録なし）。`from shared.models import AnalysisRun, RepoFile`
      で後続 issue が DML できることだけ確認（service は薄い `service/service/db.py` セッションで shared モデルに DML する規約）。

### frontend（`frontend/src/`）

- [ ] 本 issue ではフロント変更**なし**（配信 API が無いため）。各 mock の差し替えは後続が行う：
      Overview は `frontend/src/lib/mock/overview-mock.ts`、Matrix は `client.listDebts` / `client.getDebt`
      （`frontend/src/lib/api/client.ts` の TODO）、Galaxy は `frontend/src/lib/mocks/galaxy.ts` + `galaxy-store.loadMock`。
      本 issue はこれらが将来読む共有テーブルの土台のみを用意する。

### infra（`infra/`）

- [ ] 本 issue では Terraform 変更**なし**。pgvector は image（`pgvector/pgvector:pg17`）に同梱済みで
      `CREATE EXTENSION` は migration で行う。Cloud SQL 本番でも `vector` 拡張が許可されることだけ前提確認
      （定期スキャン・拡張の本利用は 037 / 将来 issue）。

### ADR（`docs/adr/`）

- [ ] `docs/adr/` ディレクトリを新設する（CLAUDE.md の Diátaxis 構成では `docs/adr/` を規定するが、現状ディレクトリ未作成）。
- [ ] `docs/adr/0001-analysis-data-model-and-identity.md`（仮）を新設し、以下の製品判断を記録する
      （独立仕様書が存在しないため、推測でなく**決定として明示**する）：
  - **File 同一性:** File は `(run_id, path)` で同定し、run/repo 横断の同一性は `repo_file.path` で近似する
    （git rename 追跡は本 issue 範囲外。必要なら 027 の履歴拡張で扱う）。
  - **dev 識別子:** 解析（authorship/blame）は GitHub author（login / email）単位で発生するが、DevDebtOps の
    ユーザは `users.id`。両者の突合方針（`api/app/api/v1/github.py` の `resolve_installation_id` が user→github_login を
    解決する経路を参照）を決め、後続テーブル（`file_kc.dev_id` 等、029/030）が `users.id` を主、GitHub login を
    マッピング経由とする旨を確定する。
  - **run スコープ:** 解析データは project 単位（1 project = 1 repo）。`analysis_run.project_id` を全解析データの
    親スコープとし、trend は `commit_sha` + `created_at` の run 時系列から導出する。
  - **JobType 命名規約:** lowercase snake_case = queue/task path（`_`→`-`）。
  - **pgvector:** migration で拡張のみ有効化し、`vector` 列の実利用は将来 issue（重複検知・概念マッピング）に委ねる。

### テスト

- [ ] api（`backend/api/tests/`）：`alembic upgrade head` 後に `analysis_runs` / `repo_files` が存在し、
      `(run_id, path)` 一意制約と `project_id` / `job_id` の FK が効くこと（重複 path 挿入が
      `IntegrityError`、存在しない project_id 挿入が FK 違反になる）。`CREATE EXTENSION vector` が冪等
      （`IF NOT EXISTS`）で 2 回適用しても落ちないこと。
- [ ] api：`AnalysisRun` / `RepoFile` を `from shared.models import ...` で import でき、テストの
      `create_all`（autogenerate 整合）で新テーブルが作成されること（`api/app/models/__init__.py` の import 順効果の確認）。
- [ ] shared（`backend/shared/tests/`）：`AnalysisRun` / `RepoFile` モデルのスキーマ単体（必須列・default・
      tz aware の `created_at`）テスト。`shared` の依存が `pydantic` + `sqlmodel` のみのまま増えていないこと。

## 完了条件

- `uv run --directory api alembic upgrade head` で **`analysis_runs` / `repo_files`** テーブルと
  **`vector` 拡張** が作成され、`(run_id, path)` 一意制約・`project_id`（→`projects.id`）/ `job_id`（→`jobs.id`）FK が
  効くこと（観測可能：pgAdmin / psql で確認、テストで検証）。
- `from shared.models import AnalysisRun, RepoFile` が api・service の双方から可能で、`models/__init__.py`
  （shared / api 双方）の import 順（app→shared）が保たれていること。
- `JobType` 命名規約と File 同一性・dev 識別子・run スコープ・pgvector 方針が **ADR**（`docs/adr/`）に明文化され、
  後続 issue（027〜037）が参照できること。
- **本 issue で `JobType` への値追加・pipeline 登録・配信 API・フロント変更は行っていない**こと
  （土台のみ。スコープ逸脱が無いことを観測）。
- バックエンドゲート：`cd backend && uv run ruff check shared/shared api/app service/service` /
  `uv run ruff format --check shared/shared api/app service/service` / `uv run ty check shared/shared api/app service/service` /
  `uv run --directory api pytest`（+ shared）が通ること。
- `CHANGELOG.md`（日本語、Keep a Changelog）に `Added`（analysis_run / repo_file 共有テーブル + pgvector 拡張 +
  JobType 命名規約 ADR）を追記すること。

## 対象外・保留

- 個別の解析ロジック（git 履歴解析・コード重複/dead/複雑度・AI 生成痕跡・Gemini 採点/生成・依存グラフ抽出）。
  → 027（GitHub 履歴クライアント拡張）/ 028（コード負債）/ 029（KC）/ 030（知識負債）。
- KC / 負債スコア / priority の算出式と閾値の確定。→ 028 / 029（ADR 化）。
- 配信・集計 API（Overview / Matrix / Galaxy / Quiz / Learning / Agents）と enqueue ルート。→ 031 / 032 / 034 / 035 / 036。
- `file_debt` / `file_kc` / `dependency` / `code_debts` / `knowledge_debts` 等のドメイン別テーブル。
  → 各ドメイン issue が `repo_file` / `analysis_run` を親に新設。
- `JobType` への具体値追加・pipeline 三つ組登録。→ 各解析 issue。
- pgvector の `vector` 列・埋め込み類似検索の本実装（重複検知・概念マッピング）。→ 将来 issue。
- 定期スキャン（Cloud Functions + Scheduler/Pub-Sub）と trend 週次蓄積。→ 037。
- git rename 追跡による File 同一性の精緻化。→ 必要なら 027。

## 参考

- 関連 issue
  - `docs/issue/016-async-task-queue-cloud-tasks.md` — Job / JobType / enqueue / `/tasks/{pipeline}` 基盤（前提）
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 共有 ORM・Alembic・registry の様式の正典（前提・雛形）
  - `docs/issue/027-backend-github-history-client-extension.md` — git 履歴/blame/依存抽出（本 issue に依存）
  - `docs/issue/028-backend-code-debt-detection-pipeline.md` / `029`(KC) / `030`(知識負債) / `031`(Overview/Matrix API) /
    `032`(Galaxy API) / `037`(定期スキャン) — いずれも本 issue の共有テーブル・規約を参照
- 既存 backend（雛形・流用）
  - `backend/shared/shared/models/tech_stack.py` — ORM 雛形（uuid4 PK / `DateTime(timezone=True)` / UniqueConstraint）
  - `backend/shared/shared/models/job.py` — `Job`（`analysis_run.job_id` の FK 先。String 保存 enum 規約 `:29`）
  - `backend/shared/shared/models/__init__.py` — 再 export（import 順 app→shared）
  - `backend/shared/shared/enums.py` — `JobType`（`:11`）/ `JobStatus`（`:19`）の命名規約
  - `backend/api/app/alembic/versions/0003_add_tech_stacks.py` / `0004_add_projects.py`（FK・partial unique index 例） /
    `0005_add_jobs.py` — Alembic 雛形（次番 0006）
  - `backend/api/app/models/base.py:11` — naming convention（`ix/uq/ck/fk/pk`）
  - `backend/api/app/models/project.py:13` — `Project`（`analysis_run.project_id` の FK 先）
  - `backend/api/app/models/__init__.py` — shared import の配置順（app→shared）
  - `backend/service/service/registry.py:15` — pipeline 三つ組登録（後続 issue 向け）
  - `backend/service/service/pipelines/stack_analysis.py:361`（`process`）/ `:222`（`on_conflict_do_update`）— pipeline 雛形
  - `backend/service/service/services/github_git_client.py` — `TreeItem.path`（`:43`）= `repo_file.path` の素材
- フロント契約（後続 issue が本テーブルから満たす）
  - `frontend/src/lib/api/schemas.ts:180`（`fileDebtSchema`）/ `:189`（`debtTrendPointSchema`）/
    `:270`（`debtItemSchema`）/ `:303`（`starSystemSchema`・`wormholeSchema`）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — shared は pydantic+sqlmodel のみ / models import 順 app→shared /
    Annotated DI param 順序厳守 / Secret Manager・Vertex AI + ADC / PATCH 更新 / docs Diátaxis（`docs/adr/`）/
    ゲート（`uv run ruff` / `ty` / `pytest`）/ `CHANGELOG.md`（日本語・Keep a Changelog）
