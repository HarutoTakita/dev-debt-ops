# KC（Knowledge Coverage）算出パイプラインと file_kc / dependency テーブルを追加する

## 概要

Knowledge Galaxy（`frontend/src/lib/mocks/galaxy.ts` + `galaxy-store.svelte.ts:16 loadMock()`）と
Overview / Matrix の「チーム理解度」軸は、いずれも **KC（Knowledge Coverage）** ∈ [0,1] を
入力に描画される（`fileMasterySchema.kc`（`frontend/src/lib/api/schemas.ts:292`）/
`starSystemSchema.kc`（集計 KC = KC(file) 平均、`schemas.ts:305`）/ `personalGalaxySchema.org_kc`
（`schemas.ts:311`））。しかし現状バックエンドに KC を算出・永続化する経路は無く、すべてフロントの
モック直読みで成立している。

本 issue は、KC を **service の非同期解析パイプラインで算出**し、結果を shared の 2 テーブル
（`file_kc` / `dependency`）へ永続化する裏側を実装する。具体的には (1) shared に `file_kc` ORM
（`run_id` / `file_path`・`dev_id` nullable で **KC(file,dev) と集計 KC(file)** を保持・
`certified_via` / `mastery` / `computed_at`）と `dependency` ORM（`run_id` / `from_path` / `to_path`
= wormhole）を新設、(2) `JobType.KC_ANALYSIS` を追加、(3)
`service/service/pipelines/kc_analysis.py` の `process` が **027 の GitHubGitClient（authorship / blame）+
依存抽出**で KC(file,dev) を算出して `file_kc` / `dependency` に upsert、(4) api は
`POST .../analyze-kc → 202 {job_id}` で enqueue する。

> 本 issue は **KC を「算出して保存」するところまで**を担う。Galaxy の配信 API
> （`GET .../galaxy → personalGalaxySchema`）は **032** が本 issue の `file_kc` / `dependency` を
> 集計して実装する（本 issue はその前段＝データ供給）。quiz 合格による KC 加算
> （`certified_via="quiz"`）の実取り込みは **032 でなく 034**（quiz 採点）が `file_kc` へ反映する
> ため、本 issue では **後続フックのみ用意**し本実装はしない。

KC の厳密な算出式（半減期・decay 等）は独立した外部仕様書がリポジトリに存在せず（009 は §5.1 を
**参照のみ**、本文の式は不在）、本 issue では **KC → mastery マッピング閾値**（後述）を製品判断として
確定し ADR 化する。authorship / review の重み・式の確定可能な部分は明示し、根拠の無い式は捏造しない。

## 背景・目的

### 現状（KC を産む裏側が無い）

- フロントの Galaxy は `mockGalaxy`（`frontend/src/lib/mocks/galaxy.ts:5-62`）を `galaxy-store` の
  `loadMock()`（`frontend/src/lib/stores/galaxy-store.svelte.ts:16`）が `observed:true` で上書きして
  描画するだけ。`client.ts` に galaxy / KC 用の関数は **一切無い**（grep で 0 件）。
- KC の見た目マッピング（`mastery`）は 009 §の表（`docs/issue/009-knowledge-galaxy-2d-map.md:284-289`）に
  `star ≥0.7 / dim_star 0.4–0.7 / black_hole <0.4（接触あり）/ unexplored 未接触` と確定済みで、
  mock もこれに整合（`galaxy.ts:14` の 0.23=black_hole、`:16` の 0.78=star 等）。だが
  この閾値を **適用して mastery を決める実装**がバックエンドに無い。
- KC(file,dev)（ファイル×開発者）は **git の authorship / blame** が前提だが、その取得層は 027 で
  service に新設される（`docs/issue/027-backend-github-history-client-extension.md`）。本 issue は
  027 の取得層を **消費して KC を算出**する最初の利用者。
- 依存（wormhole = `wormholeSchema.from/to`、`schemas.ts:298-301`）も同様にモック
  （`galaxy.ts:55-61`）のみで、永続テーブルが無い。027 の依存抽出ヘルパ（`ImportEdge`）は
  「`dependency` テーブルへの upsert は 029 が所有」と明記される
  （`docs/issue/027-...:78-79, 223`）。本 issue がその所有者。

### 目的

1. shared に `file_kc` / `dependency` テーブルを新設し、KC(file,dev) / KC(file) / mastery / wormhole を
   永続化できるようにする（api 所有の Alembic で作成）。
2. `JobType.KC_ANALYSIS` を追加し、service に `kc_analysis` パイプライン三つ組を登録する。
3. `process` が 027 の authorship / blame + 依存抽出を使って KC(file,dev) を算出し、集計 KC(file) を導出、
   mastery 閾値を適用して `file_kc` / `dependency` を upsert する。
4. api は `POST .../analyze-kc → 202 {job_id}` の enqueue に徹し、ポーリングは既存
   `GET /api/v1/jobs/{id}` を流用する。
5. KC → mastery マッピング閾値と authorship / review の重み配分を **本 issue で確定し ADR 化**する。

### 前提 issue（depends_on）

- **issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — 解析データ基盤
  （共有テーブル `analysis_run` / `repo_file`、`JobType` 拡張規約、pgvector 拡張、**File 同一性 /
  dev 識別子（`users.id` か GitHub login か）の正規化 ADR**）。本 issue の `file_kc.run_id` /
  `dependency.run_id` は 026 の `analysis_run.id` を、`file_path` は `repo_file` を File 同一性アンカーとして
  参照する。`dev_id` の正規形（`users.id` / GitHub login）は 026 ADR に従う。
- **issue 027** `docs/issue/027-backend-github-history-client-extension.md` — GitHubGitClient の
  commit 履歴 / blame / PR レビューメタ取得拡張、**authorship マッピングユーティリティ**
  （GitHub author ↔ `users.id` 突合）、**依存グラフ抽出ヘルパ**（`ImportEdge` = `from_path`/`to_path`）。
  本 issue の `process` はこれらを `process(request, ctx)` 内から呼ぶ最初の利用者。
- （前提として 018 が完了済み）`docs/issue/018-stack-analysis-async-job-on-service.md` — service の
  パイプライン三つ組規約・方式 B・`PipelineContext.session` 利用・`finally` 後始末。本 issue は
  `stack_analysis.py` を雛形にする。

> 本 issue は KC スコアの **算出と保存**が主眼。検知系（028 コード負債 / 030 知識負債）とは別ドメインだが、
> `file_kc.knowledge_coverage`（= KC(file)）は 030 が join して `knowledge_debts.knowledge_coverage` を
> 埋める供給元になる（`docs/issue/030-...` 参照）。重複定義を避けるため **KC の本算出はすべて本 issue が所有**する。

### 独自性（他 issue との差分）

028（コード負債）は `knowledge_coverage` を **暫定値**として持つだけ（028 が「本算出は 029」と明記、
`docs/issue/028-backend-code-debt-detection-pipeline.md`）。032（Galaxy 配信）は本 issue の `file_kc` /
`dependency` を **読んで集計するだけ**で算出しない。本 issue は **KC(file,dev) を git から実際に計算し、
mastery を確定し、wormhole を永続化する唯一の場所**である。式の確定（閾値・重み）も本 issue が ADR で行う。

## データモデル（新規 / 変更テーブル）

shared（`backend/shared/shared/models/`、`pydantic` + `sqlmodel` のみ）に 2 テーブルを新設する。
雛形は `tech_stack.py`（`uuid4` PK・`DateTime(timezone=True)`・JSON 列・`UniqueConstraint`、
`backend/shared/shared/models/tech_stack.py:19-45`）。Alembic は **api 所有**（`backend/api/app/alembic/`、
雛形 `0003_add_tech_stacks.py` / `0005_add_jobs.py`、連番は **026 の 0006 の次**＝本 issue は `0007` 想定。
026 未確定の間は 026 確定後に番号整合）。service は DML のみ（マイグレーションを持たない）。

### 新規テーブル `file_kc`（`backend/shared/shared/models/file_kc.py`）

KC(file,dev)（ファイル×開発者）と集計 KC(file) を **1 テーブルで `dev_id` の nullable で両立**させる。

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`default_factory=uuid.uuid4`、PK） | `tech_stack.py:28` と同方式 |
| `run_id` | `uuid.UUID`（FK → `analysis_run.id`、026） | スナップショット軸。026 確定後に名称整合 |
| `file_path` | `str` | `fileMasterySchema.path`（`schemas.ts:290`）。`repo_file`（026）と join 可 |
| `module` | `str` | `fileMasterySchema.module`（`schemas.ts:291`）= 星系 = ディレクトリ。032 の星系集計に使用 |
| `dev_id` | `uuid.UUID \| None`（nullable、026 の dev 識別正規形に従う） | **`None` = 集計 KC(file)** 行 / 非 `None` = KC(file,dev) 行 |
| `github_handle` | `str \| None` | 027 の authorship 突合結果。`users.id` 未突合 author は handle のみ保持（捏造しない、027 方針） |
| `kc` | `float`（0..1） | `fileMasterySchema.kc`（`schemas.ts:292`）= KC ∈ [0,1] |
| `mastery` | enum `star/dim_star/black_hole/unexplored` | `masteryStatusSchema`（`schemas.ts:287`）。下記閾値で `kc` から導出 |
| `certified_via` | enum `quiz/authorship/review`（nullable） | `certifiedViaSchema`（`schemas.ts:222`）。本 issue は `authorship`（/`review`）。`quiz` は 034 が更新 |
| `computed_at` | `datetime`（tz aware） | 算出時刻（`DateTime(timezone=True)`、`tech_stack.py:31-34` 同方式） |

- **`mastered`（`fileMasterySchema.mastered`、`schemas.ts:295`、default false）は列にしない。**
  032 が配信時に「`mastery==="star"` を mastered 簡易認定」する（009 §5.5 簡易版、`009:87`）。
  実 mastered 認定（quiz 連携）は 034 依存で後続。
- **一意制約:** `(run_id, file_path, dev_id)` に `UniqueConstraint`
  （`tech_stack.py:26` の `uq_*` 命名規約に倣う。upsert の競合キー。`dev_id IS NULL` の集計行と
  dev 行を区別。`NULL` を含む一意制約の挙動は migration で部分インデックス等を要検討＝下記参照）。

### 新規テーブル `dependency`（`backend/shared/shared/models/dependency.py`）

027 の依存抽出ヘルパ（`ImportEdge`）が返すリポジトリ内ファイル間依存を永続化する。
`wormholeSchema.from/to`（`schemas.ts:298-301`）へ射影される。

| 列 | 型 | 由来 / 備考 |
|---|---|---|
| `id` | `uuid.UUID`（`default_factory=uuid.uuid4`、PK） | `tech_stack.py:28` と同方式 |
| `run_id` | `uuid.UUID`（FK → `analysis_run.id`、026） | スナップショット軸 |
| `from_path` | `str` | `wormholeSchema.from`（`schemas.ts:299`）= 依存元ファイルパス |
| `to_path` | `str` | `wormholeSchema.to`（`schemas.ts:300`）= 依存先ファイルパス |
| `computed_at` | `datetime`（tz aware） | 算出時刻 |

- **一意制約:** `(run_id, from_path, to_path)` に `UniqueConstraint`（同一 run 内の重複辺を抑止）。

### KC → mastery マッピング閾値（本 issue で確定・ADR 化）

009 §の表（`docs/issue/009-knowledge-galaxy-2d-map.md:284-289`）を **正典**として確定する
（mock も整合済み）。`kc` から `mastery` を導出する：

| `kc` | `mastery` | 意味 |
|---|---|---|
| `>= 0.7` | `star` | マスター済み |
| `0.4 – 0.7`（`0.4 <= kc < 0.7`） | `dim_star` | 部分理解 |
| `< 0.4` かつ **接触あり**（authorship / blame に痕跡あり） | `black_hole` | 触ったが未理解 |
| **接触なし**（authorship / blame の痕跡が無い） | `unexplored` | 未接触 |

- **低 KC フラグ**は `kc < 0.4`（007 / 009 と整合、`docs/issue/007-overview-debt-matrix-dashboard.md` の
  低 KC フラグ条件）。`black_hole` と `unexplored` の境界は「接触の有無」（blame に当該 dev /
  チームの痕跡があるか）で分ける。

### authorship / review の重み（本 issue で確定・ADR 化）

外部仕様書に KC(file,dev) の数式は無い（009 は §5.1 を参照のみ、本文式は不在）。半減期 / decay も
明示無し＝**不明**。本 issue では「git authorship のみで暫定算出」する MVP の式を **製品判断として明示**し、
捏造した精密式は導入しない。確定する方針：

- **KC(file,dev) は 027 の authorship / blame から導出**する。MVP では「当該 dev の blame 行比率
  （ファイル内で当該 dev が最終変更した行の割合）」を素の重みとし、`certified_via="authorship"` として記録する。
- **`certified_via="review"`**（PR レビューのみで著者でない）の dev は、027 の PR レビューメタが取れる場合に
  **authorship より低い重み**で加算する（009 §5.5「形式レビューのみ」の区別。重み配分の具体値は ADR で確定）。
- **`certified_via="quiz"` による KC 加算は本 issue では行わない**（034 が `file_kc` を更新するフックのみ用意）。
- **KC(file)（集計、`dev_id IS NULL` 行）** は当該ファイルの dev 行の KC を集約した値とする
  （MVP は最大値 or 平均。032 が `starSystemSchema.kc` で「KC(file) 平均」を星系集計に使う前提＝
  `schemas.ts:305` と整合する集約方針を ADR で確定）。decay / 時間減衰は不明のため MVP では入れない。

> 上記の閾値・重み・集約方針は `docs/adr/` に新規 ADR として記す（026 の File 同一性 / dev 識別子 ADR、
> 027 の取得方式 ADR と相互参照）。「式が不明な部分は不明と明記し、MVP の暫定式であることを ADR に残す」。

## API（`/api/v1/...`）

api は **enqueue + `202` + ポーリング**に徹する（`stack.py:105-143` を雛形）。KC / Galaxy の **配信**
（`GET .../galaxy`）は 032 が `file_kc` / `dependency` を集計して実装する（本 issue は配信 GET を持たない）。

### `POST /api/v1/github/repositories/{owner}/{repo}/analyze-kc` → `202`

- `stack.py::analyze_stack`（`backend/api/app/api/v1/stack.py:105-143`）と同型。`InstallationIdDep`
  （`backend/api/app/api/v1/github.py`）で installation_id を解決し、方式 B（`installation_id` のみ
  payload に載せる）で
  `enqueue_job(session, dispatcher, blob_client, job_type=JobType.KC_ANALYSIS, payload=..., created_by=current_user.id)`
  （`backend/api/app/services/job_orchestrator.py`）を呼ぶ。
- レスポンスは既存 `JobEnqueuedOut`（`backend/api/app/schemas/job.py`、`{job_id, status}`）を流用。
  フロントは `analyzeStackJobSchema`（`schemas.ts:157` 相当）と同形で受ける。
- 進捗・完了は既存 `GET /api/v1/jobs/{id}`（`backend/api/app/api/v1/jobs.py`）でポーリング。
  `Job.result_data` に算出サマリ（file 件数・dependency 件数・trace）が入る。**KC の配信
  （`personalGalaxySchema`、`schemas.ts:309`）は 032 の `GET .../galaxy` に一致させる。**

> ルート粒度: 本 issue の起動トリガは既存 `stack.py` と同じ `/github/repositories/{owner}/{repo}/...`
> 配下に置く（`stack.py:106` の実ルート形に合わせ、028 と一貫）。projects スコープ
> （`/orgs/{slug}/projects/{project_slug}/...`、`projects.py:18-42`）への寄せ・OrgScope 認可は
> 配信 API を持つ 031 / 032 でルート設計を確定する。本 issue では既存 `analyze-stack` と同じ認可
> （`CurrentUser` + installation 解決）を踏襲する。

### 認可

`stack.py` 同様 `CurrentUser`（`backend/api/app/api/deps.py`）+ installation_id 解決。**Annotated DI param
順序を変更しない**（CLAUDE.md「`Annotated[T, Depends(f)]` deps の宣言順序を変えない」＝pytest teardown の
DROP TABLE デッドロック回避）。

## パイプライン・非同期

### `JobType` 追加（`backend/shared/shared/enums.py:11-16`）

`JobType` に `KC_ANALYSIS = "kc_analysis"` を追加（lowercase snake_case = queue path `kc-analysis`、
`enums.py:1-5` の規約）。

### request / result スキーマ（`backend/shared/shared/schemas/kc_analysis.py`）

`stack_analysis.py`（`backend/shared/shared/schemas/stack_analysis.py`）を雛形に：

- `KcAnalysisRequest(JobRequestBase)`: `owner` / `repo` / `branch: str = "main"` / `github: GitHubRef`
  （`installation_id` のみ＝方式 B、`stack_analysis.py:45-55` の `GitHubRef` を再利用）/ `project_id: str` /
  `requested_by: str`（監査用）。026 確定後に `run_id` を載せるかを整合（`analysis_run` を api が事前生成して
  渡すか、service が生成するかは 026 の規約に従う）。
- `KcAnalysisResult(JobResultBase)`: `owner` / `repo` / `branch` / `file_kc_count: int` /
  `dependency_count: int` / `trace: list[str]`（算出ステップ）。`Job.result_data` に書かれ
  （camelCase, `by_alias=True`、`stack_analysis.py` ヘッダ参照）、`GET /jobs/{id}` で読まれる。
  `JobRequestBase` / `JobResultBase` は `backend/shared/shared/schemas/job.py:12-27`。

### registry 三つ組登録（`backend/service/service/registry.py:15-18`）

`PIPELINES` に
`JobType.KC_ANALYSIS.value: (KcAnalysisRequest, KcAnalysisResult, kc_analysis.process)` を追加
（`stack_analysis` の隣）。重い依存（027 の git 履歴 / blame / 依存抽出）は service のみに置き
shared / api に漏らさない（`registry.py:1-8` の方針）。

### `process(request, ctx)`（`backend/service/service/pipelines/kc_analysis.py`）

`stack_analysis.py::process`（`backend/service/service/pipelines/stack_analysis.py:361-389`）を雛形に：

1. `ctx.session` が `None` なら `RuntimeError`（`stack_analysis.py:368`、`PipelineContext.session` =
   `backend/shared/shared/pipelines/context.py:23`）。
2. 方式 B でトークン mint（`stack_analysis.py:332-342` の `_mint_installation_token` と
   `service.services.github_app.GitHubAppService` を流用。027 が共通化したヘルパがあればそれを使う）。
   027 拡張版 `GitHubGitClient` で **authorship / blame** を取得する。
3. **authorship マッピング**（027）で GitHub author ↔ `users.id`（/ `github_handle`）を突合し、
   KC(file,dev) を算出する（上記「authorship / review の重み」の MVP 式）。`mastery` 閾値を適用。
4. **依存抽出**（027 の `get_file_content` + import 解析ヘルパ → `ImportEdge`）でリポジトリ内ファイル間の
   `from_path`/`to_path` を生成する。外部パッケージ import は wormhole 対象外（027 方針）。
5. KC(file)（集計、`dev_id IS NULL` 行）を dev 行から導出する。
6. `ctx.session` で `file_kc` / `dependency` を **upsert**する（`stack_analysis.py:213-233 save_stack` の
   `pg_insert(...).on_conflict_do_update(...)` パターン。競合キーは上記 `UniqueConstraint`）。
   `client.aclose()` は `finally`（`stack_analysis.py:373-376` の後始末規約）。
7. `KcAnalysisResult` を返す（`shared.worker.run_task` が冪等に `Job` ライフサイクル / `result_data` を書く）。

> **冪等性（Cloud Tasks は at-least-once）:** `Job` ライフサイクルは `shared.worker.run_task` が吸収する
> （`stack_analysis.py` ヘッダ）。`file_kc` / `dependency` の二重書き込みは `UniqueConstraint` +
> `on_conflict_do_update` で吸収する（再配送で行が重複しない）。

### 定期スキャン

KC の再算出トリガ（authorship / 依存の鮮度更新）は Cloud Functions / Cloud Scheduler / Pub-Sub で
project を巡回 enqueue する（CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub トリガー）」）。
基盤の Terraform は **037** が担当し、本 issue は手動トリガ（`POST .../analyze-kc`）+ パイプラインのみ。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `shared/shared/models/file_kc.py` を新設（上記 `file_kc` テーブル。`tech_stack.py:19-45` 雛形・
      `uuid4` PK・`DateTime(timezone=True)`・`(run_id, file_path, dev_id)` `UniqueConstraint`）。
- [ ] `shared/shared/models/dependency.py` を新設（上記 `dependency` テーブル・
      `(run_id, from_path, to_path)` `UniqueConstraint`）。
- [ ] `shared/shared/models/__init__.py`（`backend/shared/shared/models/__init__.py:1-6`、現 `Job` / `TechStack`）に
      `FileKc` / `Dependency` を追記し re-export（import 順は **app→shared** 規約。autogenerate 用）。
- [ ] `shared/shared/enums.py`（`:11-16`）の `JobType` に `KC_ANALYSIS = "kc_analysis"` を追加。
- [ ] `shared/shared/schemas/kc_analysis.py` を新設（`KcAnalysisRequest` / `KcAnalysisResult`、
      `stack_analysis.py:58-77` 雛形・`GitHubRef` 再利用・`JobRequestBase`/`JobResultBase` 継承）。

### api（`backend/api/app/`）

- [ ] Alembic マイグレーション（`backend/api/app/alembic/versions/`、雛形 `0003_add_tech_stacks.py` /
      `0005_add_jobs.py`）で `file_kc` / `dependency` テーブルを作成（連番は 026 の `0006` の次＝`0007` 想定。
      `base.py` の naming convention 踏襲。`dev_id IS NULL` を含む一意制約は部分ユニークインデックス等で
      意図どおり効くことを確認）。
- [ ] `backend/api/app/api/v1/stack.py:105-143` を雛形に `POST .../analyze-kc`（`JobType.KC_ANALYSIS` で
      `enqueue_job`、`202 JobEnqueuedOut`）を実装する（同ファイル内 or 新ルーター。後者なら
      `backend/api/app/api/v1/router.py:8-20` に `include_router` 追記）。
- [ ] `GET /api/v1/jobs/{id}`（`backend/api/app/api/v1/jobs.py`）はそのまま流用（KC Job の `result_data` を読む）。
      KC 配信そのもの（`file_kc` / `dependency` の集計）は **032**。

### service（`backend/service/service/`）

- [ ] `service/service/pipelines/kc_analysis.py` を新設（`process(request, ctx)`。上記 1–7 のフロー。
      `stack_analysis.py:361-389` 雛形）。
- [ ] `service/service/registry.py:15-18` の `PIPELINES` に KC 三つ組を追加。
- [ ] 027 の取得層（authorship マッピング / blame / 依存抽出ヘルパ）を `process` から呼ぶ
      （`docs/issue/027-...` のインターフェースに準拠。027 が未完なら blocked）。
- [ ] **quiz 認定フックの口だけ用意**: `certified_via="quiz"` の KC 更新は 034 が `file_kc` を更新する前提で、
      本 issue では `file_kc` の `certified_via` 列と upsert 経路を quiz が後から書き換えられる形にする
      （本 issue では quiz 加算ロジックを実装しない）。

### frontend（`frontend/src/`）

- [ ] **本 issue では client.ts / mock の差し替えは行わない**（KC の配信 API は 032 が実装するため）。
      `frontend/src/lib/stores/galaxy-store.svelte.ts:16 loadMock()` / `frontend/src/lib/mocks/galaxy.ts` の
      差し替え地点は **032** が `getGalaxy` 新設で対応する（本 issue の `file_kc` / `dependency` を供給する側）。
      差し替え地点を参考として記録しておく。

### infra

- [ ] 方式 B の token mint に必要な Secret Manager 参照権限（`GITHUB_APP_PRIVATE_KEY`、service config）が
      service runtime SA に付与済みであることを確認（018 / 027 で配線済みの前提。新規付与は不要のはず）。
- [ ] KC の定期再算出（Cloud Functions / Scheduler）の **Terraform は 037**。本 issue では手動トリガのみで、
      インフラ追加はしない。

### test

- [ ] shared（`backend/shared/tests/`）：`file_kc` / `dependency` モデルの import / カラム / 一意制約のテスト。
- [ ] api（`backend/api/tests/`）：`POST .../analyze-kc` が `202` + `job_id` を返し、`Job` が `QUEUED` で作成され、
      `MockTaskDispatcher.dispatch` が 1 回呼ばれること（`enqueue_job` 経由、018 の analyze-stack テスト同型）。
- [ ] service（`backend/service/tests/`）：`kc_analysis.process` のパイプラインテスト（027 の authorship / blame /
      依存抽出と Gemini を **モック**）。`file_kc`（KC(file,dev) 行 + KC(file) 集計行）と `dependency`
      （wormhole）が upsert されること。`kc` から `mastery` 閾値（star/dim_star/black_hole/unexplored）が
      正しく導出されること。再配送（at-least-once）で行が二重にならない冪等性。token mint が方式 B
      （`installation_id` のみ）であること。
- [ ] service：未突合 author（`users.id` に紐づかない）が `github_handle` のみで保持され、user 紐付けを
      捏造しないこと（027 方針）。

## 完了条件

- `POST .../analyze-kc` が `202` + `job_id` を返し、api リクエストは KC 算出完了を待たずに即返る。
- service が **api リクエスト外**で 027 の authorship / blame + 依存抽出を使って KC(file,dev) を算出し、
  KC(file) を集計、mastery 閾値（`star ≥0.7 / dim_star 0.4–0.7 / black_hole <0.4 接触あり / unexplored 未接触`）を
  適用して `file_kc` / `dependency` を Cloud SQL に upsert する。
- KC → mastery 閾値と authorship / review の重み・KC(file) 集約方針が `docs/adr/` の新規 ADR に記録され、
  式が不明な部分（半減期 / decay 等）は「不明」と明記され、MVP 暫定式であることが残されている。
- `certified_via="quiz"` の KC 加算は本 issue では未実装で、034 が `file_kc` を更新できる列 / 経路が用意されている。
- `GET /api/v1/jobs/{id}` が KC Job の `status` / `result_data`（件数・trace）を返す。
- レスポンス / 永続値は snake_case 契約（`fileMasterySchema` / `wormholeSchema`、`schemas.ts:289-301`）と
  整合する形で保存され、032 がそのまま集計・配信できる（本 issue では配信しない）。
- 再配送（at-least-once）で `file_kc` / `dependency` が二重化しない（`UniqueConstraint` + `on_conflict_do_update`）。
- バックエンド：`cd backend && uv run --directory shared pytest && uv run --directory api pytest &&
  uv run --directory service pytest` /
  `uv run ruff check shared/shared api/app service/service && uv run ruff format --check shared/shared api/app service/service` /
  `uv run ty check shared/shared api/app service/service` が通る。
- `CHANGELOG.md`（日本語、Keep a Changelog）に `Added`（KC 算出パイプライン + `file_kc` / `dependency` テーブル +
  `analyze-kc` enqueue）の追記。

## 対象外・保留

- **Galaxy 配信 API**（`GET .../galaxy → personalGalaxySchema`）と client.ts / `galaxy-store.loadMock` の
  差し替え（**032** が本 issue の `file_kc` / `dependency` を集計して実装）。
- **quiz 連動の KC 加算実装**（`certified_via="quiz"` による KC(file,dev) 上昇）。本 issue は後続フック
  （列 / upsert 経路）のみ。実装は **034**（quiz 採点）が `file_kc` を更新する。
- **`mastered` の実認定**（実 quiz 連携）。032 は `mastery==="star"` の簡易認定（009 §5.5）、本認定は 034 依存。
- **KC 精密式（半減期 / decay / 重み配分の最終確定）**。外部仕様書に式が無いため MVP 暫定式を ADR 化するに留める。
- **pgvector を使った概念マッピング / 類似検索**（拡張有効化は 026、本実装は将来）。
- **dev 識別子の最終正規化方針**（026 ADR が確定）・**File 同一性アンカー / `analysis_run` の生成主体**（026）。
  本 issue は参照のみ。
- **コード負債 / 知識負債の検知**（028 / 030）。本 issue は KC(file) を 030 へ供給するのみ。

## 参考

- 関連 issue（相互参照）
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file` /
    `JobType` 拡張規約 / pgvector / File 同一性・dev 識別子 ADR（前提）
  - `docs/issue/027-backend-github-history-client-extension.md` — authorship / blame / PR 取得 +
    authorship 突合 + 依存抽出ヘルパ（`ImportEdge`）（前提・本 issue が最初の消費者）
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — パイプライン三つ組 / 方式 B / `ctx.session` /
    `finally` 後始末の雛形
  - `docs/issue/028-backend-code-debt-detection-pipeline.md` — `knowledge_coverage` 暫定値（本算出は本 issue）
  - `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — `file_kc`（KC(file)）を join する消費先
  - `docs/issue/032-backend-galaxy-personal-kc-api.md` — `file_kc` / `dependency` を集計して `GET .../galaxy` 配信
  - `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — `certified_via="quiz"` の KC 加算（後続）
  - `docs/issue/009-knowledge-galaxy-2d-map.md` — KC → mastery 閾値（`:284-289`）・メタファー語彙の出所
- 現行実装（雛形・参照対象）
  - `backend/shared/shared/models/tech_stack.py` — ORM 雛形（`:19-45`、`uuid4` PK / JSON / `UniqueConstraint`）
  - `backend/shared/shared/models/__init__.py` — re-export 地点（`:1-6`、import 順 app→shared）
  - `backend/shared/shared/enums.py` — `JobType`（`:11-16`、`KC_ANALYSIS` 追加）
  - `backend/shared/shared/schemas/stack_analysis.py` — request/result 雛形（`:45-77`、`GitHubRef` 再利用）
  - `backend/shared/shared/schemas/job.py` — `JobRequestBase` / `JobResultBase`（`:12-27`）
  - `backend/shared/shared/pipelines/context.py` — `PipelineContext.session`（`:23`）
  - `backend/service/service/pipelines/stack_analysis.py` — `process`（`:361-389`）/ `_mint_installation_token`
    （`:332-342`、方式 B）/ `save_stack` の upsert（`:213-233`）/ `finally` 後始末（`:373-376`）
  - `backend/service/service/registry.py` — `PIPELINES` 三つ組登録（`:15-18`）
  - `backend/api/app/api/v1/stack.py` — `analyze_stack`（`:105-143`、enqueue + `202`）の雛形
  - `backend/api/app/api/v1/jobs.py` — `GET /jobs/{id}` ポーリング（流用）
  - `backend/api/app/api/v1/router.py` — 新ルーター include 地点（`:8-20`）
  - `backend/api/app/alembic/versions/0003_add_tech_stacks.py` / `0005_add_jobs.py` — Alembic 雛形（次番 `0007` 想定）
- フロント契約（射影先・整合確認、本 issue では差し替えない）
  - `frontend/src/lib/api/schemas.ts` — `masteryStatusSchema:287` / `fileMasterySchema:289` /
    `wormholeSchema:298` / `starSystemSchema:303` / `personalGalaxySchema:309` / `certifiedViaSchema:222`
  - `frontend/src/lib/mocks/galaxy.ts` — `mockGalaxy`（`:5-62`、wormholes `:55-61`。差し替えは 032）
  - `frontend/src/lib/stores/galaxy-store.svelte.ts` — `loadMock()`（`:16`、差し替えは 032）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — Secret Manager 必須・方式 B 厳守・Vertex AI + ADC（API キー不使用）・
    shared は `pydantic`+`sqlmodel` のみ・`models/__init__.py` の import 順（app→shared）・`JobType` に新 pipeline 追加・
    `router.py` に新ルーター登録・Annotated DI param 順序厳守・Python snake_case・
    `uv run ruff/ty/pytest`（shared/api/service）・`bun run check/lint/test:unit` ゲート・CHANGELOG（日本語）
