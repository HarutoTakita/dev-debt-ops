# 計測粒度を抽象化し「機能（feature）」概念とクラスタリングパイプラインを導入する

## 概要

現状、コード負債・理解負債（KC）の計測単位は **ファイル固定**で、最も粗い集計でも `module = ファイルのディレクトリ`
（`backend/service/service/pipelines/kc_analysis.py` の `_module_of`）しか無い。ユーザーは「機能単位 / フォルダ単位 /
ファイル単位 / クラス単位 / 関数単位」と**粒度を切り替えて**負債を計測・表示したいが、その土台となる
(1) 粒度の抽象（enum）と (2) ディレクトリより上位の**意味的グルーピング = 機能（feature）**が存在しない。

本 issue は後続（054 ベースラインクイズ / 055 機能単位集計 API / 056 フロント粒度切替）の**基盤**として、

1. `shared` に計測粒度 enum `Granularity`（`feature` / `folder` / `file` / `class` / `function`）を新設する。
2. `shared` に **`features` / `feature_files`** の 2 テーブルを新設し、機能↔ファイルの対応を永続化する。
3. `JobType.FEATURE_CLUSTERING` を追加し、service に **Gemini（Vertex AI + ADC）でリポジトリのファイル群を機能へ
   自動クラスタリング**するパイプラインを新設する（初回解析時に実行）。
4. api は `POST .../cluster-features → 202 {job_id}` で enqueue に徹する（配信は 055 が担当）。

> **機能の導出方式は「AI 自動クラスタリング」を採用**（製品判断）。Gemini がコード構造・import 関係を読み、
> ファイル群を機能へグルーピングする。結果は `features` に永続化し、`source="ai"` を記録。将来の人手修正
> （設定 UI からの編集 = `source="manual"`）に備えて**列・upsert 経路だけ用意**し、本 issue では編集 UI は作らない。

## 背景・目的

### 現状（粒度はファイル固定・機能概念が無い）

- KC は `file_kc`（`backend/shared/shared/models/file_kc.py`）に **ファイル×開発者 / ファイル集計**で保持。
  `module` 列はあるが値は単なるディレクトリ（`kc_analysis.py` の `_module_of`：`posixpath.dirname(path)`）。
- コード負債 `code_debts` / 知識負債 `knowledge_debts` も `file_path` 単位。Overview（`debt_query.py:build_overview`）も
  ファイル単位の散布図。Galaxy（`galaxy_query.py`）の「星系」も `module = ディレクトリ`の集計に過ぎない。
- 「機能（feature）」= 「認証」「課金」「解析パイプライン」のような**製品能力単位の意味的グルーピング**は
  バックエンド・フロントのどこにも存在しない。ユーザーが「機能単位」と「フォルダ単位」を**別の粒度として**
  挙げている以上、feature はディレクトリ構造とは独立に導出する必要がある。

### 目的

1. 粒度を表す単一の enum `Granularity` を shared に定義し、以後の負債/KC 行・API・フロントが同じ語彙を使う。
2. `features` / `feature_files` テーブルで機能↔ファイルの多対多対応を永続化する（1 ファイルが複数機能に属し得る）。
3. Gemini で機能を自動クラスタリングするパイプラインを service に載せ、初回解析時に `features` を生成する。
4. api は enqueue + `202` に徹し、機能データの配信・集計は 055 に委譲する。

### 前提 issue（depends_on）

- **issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_runs` /
  `repo_file` 基盤、`shared` ORM 追加規約、`models/__init__.py` の import 順（app→shared）、Alembic 連番系列、
  File 同一性 / dev 識別子の正規化。本 issue の `features.run_id` は `analysis_runs.id` を、`feature_files.file_path`
  は File 同一性アンカーを参照する。
- **issue 027** `docs/issue/027-backend-github-history-client-extension.md` — `GitHubGitClient`（ファイル列挙 /
  内容取得）と**依存抽出ヘルパ（`ImportEdge` = `from_path`/`to_path`）**。クラスタリングの入力（ファイル一覧 +
  import グラフ）に使う。`dependency` テーブル（029 が永続化）を読めるなら機能境界の精度向上に流用する。
- **issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc` / `dependency`。本 issue は
  `dependency`（wormhole）を**機能クラスタリングのヒント**として読む（必須ではない）。

### 独自性（他 issue との差分）

029 が「KC をファイル単位で算出・保存」する唯一の場所であるのに対し、本 issue は **「ファイルを機能へ束ねる
写像」を所有する唯一の場所**である。055 は本 issue の `feature_files` を join して KC/負債を機能へロールアップ
するだけで、写像自体は作らない。クラスタリングの**非決定性**を吸収するため、結果を `features` に永続化し
run_id でスナップショットする（同一 run 内では確定値）。

## データモデル（新規テーブル）

shared（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）に 2 テーブルを新設。雛形は
`tech_stack.py`（`uuid4` PK・`DateTime(timezone=True)`・JSON 列・`UniqueConstraint`）。Alembic は **api 所有**
（`backend/api/app/alembic/versions/`、連番は既存の最終番号の次）。service は DML のみ。

### 新規 enum `Granularity`（`backend/shared/shared/enums.py`）

```python
class Granularity(str, Enum):
    FEATURE = "feature"
    FOLDER = "folder"
    FILE = "file"
    CLASS = "class"      # 後続（057）
    FUNCTION = "function"  # 後続（057）
```

- MVP で実計測・表示するのは `feature`（本系列）と既存の `file`。`folder` は既存 `module` を射影して導出可能。
  `class` / `function` は **enum 値だけ定義**し、計測は 057 へ送る（値の早期固定で API/フロント契約を安定させる）。

### 新規テーブル `features`（`backend/shared/shared/models/feature.py`）

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`default_factory=uuid.uuid4`、PK） | `tech_stack.py` と同方式 |
| `project_id` | `uuid.UUID`（index） | スコープ |
| `run_id` | `uuid.UUID`（FK → `analysis_runs.id`、index） | クラスタリング結果のスナップショット軸 |
| `key` | `str` | 安定スラッグ（例 `auth`、`billing`）。run 跨ぎの同一機能追跡に使う |
| `name` | `str` | 表示名（例「認証」） |
| `description` | `str`（default `""`） | Gemini が生成する 1〜2 行の機能説明（クイズ生成 054 の文脈にも使う） |
| `source` | `str` enum `ai`/`manual`（default `ai`） | 導出元。本 issue は `ai`。将来の人手編集は `manual` |
| `computed_at` | `datetime`（tz aware） | 算出時刻 |

- **一意制約:** `(run_id, key)` に `UniqueConstraint`（同一 run 内で機能キー重複を抑止。upsert 競合キー）。

### 新規テーブル `feature_files`（`backend/shared/shared/models/feature_file.py`）

機能↔ファイルの多対多写像（1 ファイルが複数機能に属し得る）。

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（PK） | |
| `run_id` | `uuid.UUID`（FK → `analysis_runs.id`、index） | `features.run_id` と整合 |
| `feature_id` | `uuid.UUID`（FK → `features.id`、index） | |
| `file_path` | `str`（index） | File 同一性アンカー（`repo_file` と join 可） |
| `confidence` | `float`（0..1、default `1.0`） | Gemini が返す帰属確度（曖昧なファイルの按分・表示に使用） |

- **一意制約:** `(run_id, feature_id, file_path)` に `UniqueConstraint`。

## API（`/api/v1/...`）

api は **enqueue + `202` + ポーリング**に徹する（`stack.py::analyze_stack` を雛形）。機能データの**配信**
（機能一覧・機能別ファイル）は 055 が `features`/`feature_files` を集計して実装する（本 issue は配信 GET を持たない）。

### `POST /api/v1/orgs/{slug}/projects/{project_slug}/cluster-features` → `202`

- `OrgScope`（`deps.py`）でメンバーシップ強制。`InstallationIdDep` で installation_id を解決し、**方式 B**
  （`installation_id` のみ payload 搬送）で `enqueue_job(..., job_type=JobType.FEATURE_CLUSTERING, ...)`。
- レスポンスは既存 `JobEnqueuedOut`（`{job_id, status}`）。進捗・完了は既存 `GET /api/v1/jobs/{id}` でポーリング。
- **Annotated DI param 順序を変更しない**（`deps.py` 規約、CLAUDE.md）。

## パイプライン・非同期

### `JobType` 追加（`backend/shared/shared/enums.py`）

`FEATURE_CLUSTERING = "feature_clustering"`（lowercase snake_case → queue path `feature-clustering`）。

### request / result スキーマ（`backend/shared/shared/schemas/feature_clustering.py`）

`stack_analysis.py` を雛形に `JobRequestBase` / `JobResultBase` を継承、`GitHubRef`（方式 B）再利用。

- `FeatureClusteringRequest`: `owner` / `repo` / `branch="main"` / `github: GitHubRef` / `project_id` / `requested_by`。
- `FeatureClusteringResult`: `owner` / `repo` / `branch` / `feature_count` / `file_count` / `trace: list[str]`。

### `process(request, ctx)`（`backend/service/service/pipelines/feature_clustering.py`）

`stack_analysis.py::process` を雛形に：

1. `ctx.session` が `None` なら `RuntimeError`。方式 B でトークン mint（`GitHubAppService`、`_mint_installation_token`）。
2. `GitHubGitClient` でソースファイル一覧（+ 必要なら内容の要約）と、027 の依存抽出 / 029 の `dependency` を取得し、
   **import グラフ**を組む（機能境界の主要シグナル）。
3. Gemini（`gemini_stack_service`、Vertex AI + ADC、`response_mime_type="application/json"`）に
   「ファイルパス一覧 + 依存関係」を渡し、**機能名 / key / 説明 / 所属ファイル + confidence** を JSON で返させる。
   ファイル数が `_MAX_FILES` を超える場合はディレクトリ要約等で入力を圧縮する（プロンプト肥大の回避）。
4. `features` / `feature_files` を `pg_insert(...).on_conflict_do_update(...)` で **upsert**（競合キーは上記
   `UniqueConstraint`）。`client.aclose()` は `finally`。
5. `FeatureClusteringResult` を返す（`shared.worker.run_task` が冪等に `Job` ライフサイクル / `result_data` を書く）。

> **冪等性（Cloud Tasks は at-least-once）:** クラスタリングは非決定的なため、再配送時に**機能集合が揺れない**
> よう `(run_id, key)` をスナップショットの一意キーとし、同一 run の再実行は upsert で吸収する。run を跨ぐ
> 機能追跡は `key` の安定性に依存（プロンプトで「既存 key を尊重」する指示を将来検討、本 issue は単 run で確定）。

### 初回解析パイプラインへの組み込み

フロントの解析ラン（`frontend/src/lib/stores/analysis-run-store.svelte.ts` の 5 ステージ：detect_code /
detect_knowledge / analyze_galaxy(=kc_analysis) / plan_learning / loop_agents）に対し、機能クラスタリングは
**KC 算出（kc_analysis）より前**に走る必要がある（054/055 が `feature_files` を消費するため）。本 issue では
`cluster-features` を**手動トリガで叩ける**ところまでを担い、初回解析ランへのステージ組み込み（順序保証）は
054 と合わせて配線する（本 issue では enqueue 経路のみ用意）。

## タスク

### shared（`backend/shared/shared/`）
- [ ] `enums.py` に `Granularity` enum と `JobType.FEATURE_CLUSTERING` を追加。
- [ ] `models/feature.py` / `models/feature_file.py` を新設（上記テーブル・`UniqueConstraint`・`tech_stack.py` 雛形）。
- [ ] `models/__init__.py` に `Feature` / `FeatureFile` を import 順 app→shared で re-export 追記。
- [ ] `schemas/feature_clustering.py` を新設（`FeatureClusteringRequest` / `FeatureClusteringResult`）。

### api（`backend/api/app/`）
- [ ] Alembic マイグレーションで `features` / `feature_files` を作成（連番は既存最終番号の次。naming convention 踏襲）。
- [ ] `api/v1/` に `POST .../cluster-features`（`JobType.FEATURE_CLUSTERING` enqueue、`202 JobEnqueuedOut`）を実装し
      `router.py` に include。`GET /jobs/{id}` はそのまま流用。

### service（`backend/service/service/`）
- [ ] `pipelines/feature_clustering.py` を新設（上記 1–5）。`registry.py` の `PIPELINES` に三つ組登録。
- [ ] `gemini_stack_service` に機能クラスタリング用プロンプト/呼び出しを追加（既存 Vertex AI + ADC を流用拡張）。
- [ ] 027 の依存抽出 / 029 の `dependency` を入力に使う（取得層が未完なら blocked を明記）。

### test
- [ ] shared：モデル import / カラム / 一意制約。`Granularity` enum 値。
- [ ] api：`POST .../cluster-features` が `202` + `job_id`、`Job` が `QUEUED`、`MockTaskDispatcher.dispatch` 1 回。
- [ ] service：`feature_clustering.process` が Gemini / GitHub をモックして `features` / `feature_files` を upsert。
      再配送（at-least-once）で機能集合が二重化しない冪等性。方式 B で token mint。

## 完了条件
- `POST .../cluster-features` が `202` + `job_id` を返し、service が api リクエスト外で Gemini クラスタリングを実行、
  `features` / `feature_files` を Cloud SQL に upsert する。
- `Granularity` enum が shared に定義され、`feature`/`folder`/`file` は実値、`class`/`function` は将来枠として固定される。
- 同一 run の再配送で機能集合が二重化しない（`UniqueConstraint` + `on_conflict_do_update`）。
- GitHub トークンが方式 B（`installation_id` のみ搬送、service が Secret Manager から mint）。
- バックエンド：`uv run ruff check/format --check`・`uv run ty check`・`pytest`（shared/api/service）が通る。
- `CHANGELOG.md`（日本語）に `Added`（粒度 enum + 機能クラスタリングパイプライン + `features`/`feature_files` テーブル）を追記。

## 対象外・保留
- **機能データの配信 API / 集計**（機能一覧・機能別 KC/負債）→ **055**。
- **機能の人手編集 UI / 設定**（`source="manual"`）→ 将来（列と upsert 経路のみ本 issue で用意）。
- **クラス単位 / 関数単位の計測**（AST 解析が必要）→ **057**（enum 値だけ先行定義）。
- **run 跨ぎの機能同一性追跡の高度化**（key 安定化プロンプト等）→ 将来。

## 参考
- 既存実装（雛形）：`backend/service/service/pipelines/stack_analysis.py`（`process` / 方式 B token mint /
  `save_*` の upsert / `finally` 後始末）、`backend/service/service/registry.py`（三つ組登録）、
  `backend/service/service/services/gemini_stack_service.py`（Vertex AI + ADC）、
  `backend/api/app/api/v1/stack.py`（enqueue + 202）、`backend/shared/shared/models/tech_stack.py`（ORM 雛形）。
- 機能境界のシグナル：`backend/service/service/pipelines/kc_analysis.py`（`_module_of`）、`dependency` テーブル（029）。
- 関連 issue：[026 解析データ基盤](./026-backend-analysis-data-model-and-shared-tables.md)、
  [027 GitHub 履歴/依存抽出](./027-backend-github-history-client-extension.md)、
  [029 KC パイプライン](./029-backend-kc-knowledge-coverage-pipeline.md)、
  [055 機能単位の集計 API](./055-backend-feature-granularity-debt-aggregation-api.md)、
  [057 多粒度・コード負債拡張](./057-multi-granularity-code-debt-rollout.md)。
- 規約：`CLAUDE.md` / `backend/CLAUDE.md`（Secret Manager 必須・Vertex AI + ADC・方式 B・Annotated DI 順序厳守・
  `models/__init__.py` import 順・JobType 追加・`router.py` 登録・snake_case 配信・CHANGELOG 日本語）。
