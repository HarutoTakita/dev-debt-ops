# Galaxy 個人 KC マップ配信 API を実装する

## 概要

Knowledge Galaxy 個人ビュー（`docs/issue/009-knowledge-galaxy-2d-map.md`）は、現在
フロント専用で `frontend/src/lib/mocks/galaxy.ts` の `mockGalaxy` を
`frontend/src/lib/stores/galaxy-store.svelte.ts:16` の `loadMock()` が直読みしているだけで、
**裏側の配信 API は存在しない**。

本 issue は、issue 029 が算出・永続化する `file_kc` / `dependency`（KC(file) と依存グラフ）を
**module 単位の星系へ集計し、`personalGalaxySchema`（`frontend/src/lib/api/schemas.ts:309`）の形で
配信する api 層**を実装する。

- `GET .../galaxy` → `PersonalGalaxyOut`（`developer` / `org_kc` / `observed` / `systems`（`starSystem`）/ `wormholes`）。
  module 単位で星系へ集計し、KC(file) を 029 の閾値で `star` / `dim_star` / `black_hole` / `unexplored` に投影。
- `POST .../analyze-galaxy` → `202 {job_id}`（029 の `kc_analysis` パイプラインを enqueue。`stack.py:105` の雛形を踏襲）。
- フロント `client.ts` に `getGalaxy` / `analyzeGalaxy` を新設し、`galaxy-store.loadMock()` を実 API 呼び出しへ差し替える。

api は **enqueue + 集計/配信 + ポーリング** に徹する（issue 018 と同方針）。KC 算出式・KC(file,dev) の保持は
029 が所有し、本 issue は **その集計と投影のみ**を担う。レスポンスは `schemas.ts` が snake_case を維持しているため、
**素の `BaseModel`（`stack.py:57` の `TechStackOut` パターン）で snake_case のまま配信**する
（`SharedBaseModel` の `by_alias` camelCase は使わない）。

## 背景・目的

### 現状（フロントのみ・モック）

- `frontend/src/lib/api/schemas.ts:285-321` に `masteryStatusSchema` / `fileMasterySchema` /
  `wormholeSchema` / `starSystemSchema` / `personalGalaxySchema` が確定済み（全 snake_case）。
- `frontend/src/lib/mocks/galaxy.ts:5` の `mockGalaxy`（developer `"you"`, org_kc `0.62`, observed `false`,
  5 モジュール `auth`/`services`/`utils`/`billing`/`api` × 各 2-4 ファイル, wormholes 5 本）。
- `frontend/src/lib/stores/galaxy-store.svelte.ts:13` で `myKc = Math.round(org_kc*100)`、
  `loadMock()` が `{ ...mockGalaxy, observed: true }` を代入。`client.ts` に galaxy 関数は皆無
  （`grep galaxy frontend/src/lib/api/client.ts` ヒット 0）。
- issue 009 §390-398 の MVP/Future 表は「データ取得＝`galaxy-store` 内モック / Future＝実 API
  `GET /api/v1/.../galaxy` 等」と明記（009:398）。本 issue がその Future の配信層を作る。

### 目的

1. 029 が永続化する `file_kc`（KC(file) / mastery）と `dependency`（from_path/to_path = wormhole）を
   読み、**module 単位で `starSystem` に集計**して `PersonalGalaxyOut` を組み立てる `GET .../galaxy` を api に追加する。
2. `POST .../analyze-galaxy` で 029 の `kc_analysis` パイプラインを **enqueue（`202 {job_id}`）** し、
   既存 `GET /api/v1/jobs/{id}` ポーリングで完了を待てるようにする（`stack.py:105` の雛形）。
3. フロント `client.ts` に `getGalaxy` / `analyzeGalaxy` を新設し、`galaxy-store` のモック読み込みを
   実 API へ差し替える（009:69 が「本実装ではここを実 API に差し替える」と前提）。

### 前提 issue（depends_on）

- **issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` —
  `shared` に `file_kc` ORM（`run_id` / `file_path` / `dev_id` nullable で KC(file,dev) と集計 KC(file) /
  `certified_via` / `mastery`[`star`/`dim_star`/`black_hole`/`unexplored`] / `computed_at`）と
  `dependency` ORM（`run_id` / `from_path` / `to_path` = wormhole）を新設し、
  `kc_analysis` パイプラインで KC を算出・upsert する。**KC→mastery の閾値**（`star≥0.7` /
  `dim_star 0.4-0.7` / `black_hole<0.4 接触あり` / `unexplored 未接触`）と `JobType.kc_analysis` の追加、
  および `analysis_run` / `repo_file`（issue 026）が確定していることが前提。本 issue は **029 の閾値を
  再定義せず引用**し、その上に集計・投影・配信のみを載せる。

> 本 issue は新しい KC 算出ロジックを書かない。**029 が産んだ `file_kc` / `dependency` を読み、
> Galaxy 形へ集計・投影して配信する** ことが主眼である。

## データモデル

**新規テーブルは作らない。** 本 issue は読み取り・集計のみで、データの実体は前提 issue が所有する：

| テーブル | 所有 issue | 本 issue での用途 |
|---|---|---|
| `file_kc`（`run_id` / `file_path` / `dev_id` nullable / `kc` / `mastery` / `certified_via` / `computed_at`） | 029（shared ORM） | 星（ファイル）の KC と mastery を読む。`dev_id` で KC(file,dev) と集計 KC(file) を出し分け |
| `dependency`（`run_id` / `from_path` / `to_path`） | 029（shared ORM） | wormhole（from/to）を読む |
| `analysis_run`（`project_id` / `commit_sha` / `branch` / `kind` / `job_id` / `status` / `created_at`） | 026（shared ORM） | 最新 run（`status=COMPLETED`）を解決し、その `run_id` で `file_kc` / `dependency` を絞る |
| `projects`（`repo_owner` / `repo_name` / `default_branch`） | 既存（`backend/api/app/models/project.py:13`） | `/orgs/{slug}/projects/{project_slug}` スコープ解決 |

- module（星系）は `file_kc.file_path` のディレクトリ先頭（または 029 が `repo_file` に持つ module 列）から導出。
  正規化規約は 029/026 の File 同一性方針に従う（推測でディレクトリ分割規則を新設しない）。
- 星系集計 KC（`starSystem.kc`）= その module に属する `file_kc.kc`（KC(file)）の平均
  （`schemas.ts:305` コメント「KC(file) 平均」、009:231 に整合）。
- `org_kc`（`personalGalaxy.org_kc`、サイドバー pill 用の自分の KC%）= developer に紐づく KC(file,dev) の
  集計値。029 が組織/個人 KC をどこで保持するか（集計クエリか保存列か）に従う。式の確定は 029 に委ね、
  本 issue は 029 が供給する値を読むに留める。
- **Alembic 不要**（テーブル新設なし）。`shared/shared/models/__init__.py` への追記も 029 が行う。

> KC 算出式・mastery 閾値・KC(file,dev) の保持主体は **029 が所有**。本 issue でこれらを再定義・捏造しない。

## API

ルートは `projects.py` の `/orgs/{slug}/projects/{project_slug}/...` スコープに揃える（新機能データは原則
プロジェクト単位、`projects.py:18-169`）。認可は `OrgScope`（`deps.py:64`、org メンバー）。
Annotated DI の **param 順序を変更しない**（CLAUDE.md `Annotated DI param 順序`）。
レスポンスは **snake_case 配信**（素の `BaseModel`、`stack.py:57` パターン）で `personalGalaxySchema` に一致させる。

### `GET /api/v1/orgs/{slug}/projects/{project_slug}/galaxy`

- 一致させる Zod: `personalGalaxySchema`（`schemas.ts:309`）→ `PersonalGalaxyOut`。
  - `developer: str` — current_user ↔ GitHub login マッピングで解決（後述）。
  - `org_kc: float`（0..1）— 自分の KC%（pill 用）。
  - `observed: bool` — 完了した `analysis_run`（029 の `kind=kc_analysis`）が存在すれば `true`、無ければ `false`。
    未観測時はフロントが `ComingSoonPlaceholder` を出す契約（009:312, 009:118-120）。
  - `systems: list[StarSystemOut]` — `StarSystemOut{module: str, kc: float(0..1), files: list[FileMasteryOut]}`。
    - `FileMasteryOut{path, module, kc(0..1), mastery, mastered: bool}`（`fileMasterySchema`、`schemas.ts:289`）。
    - `mastery` は 029 の閾値で投影された `file_kc.mastery` をそのまま使う。
    - `mastered` は簡易認定 = `mastery == "star"`（009:87・009:396、quiz 連動の実認定は 034 依存で本 issue は対象外）。
  - `wormholes: list[WormholeOut]` — `WormholeOut{from: str, to: str}`（`wormholeSchema`、`schemas.ts:298`。
    `from` は Python 予約語のため `alias="from"` 等で対応）。
- 振る舞い: 最新の完了 `analysis_run` を解決 → その `run_id` で `file_kc`（developer 解決後は KC(file,dev)）と
  `dependency` を取得 → module 単位で星系に畳み込み → `PersonalGalaxyOut` を返す。
  未観測（run なし）は `observed=false`・`systems=[]`・`wormholes=[]` で `200` を返す
  （404 ではなく observed フラグで表現。フロントが `observed` で分岐するため）。

### `POST /api/v1/orgs/{slug}/projects/{project_slug}/analyze-galaxy`

- `response_model=JobEnqueuedOut`（`backend/api/app/schemas/job.py`）、`status_code=202`。
- 029 の `JobType.kc_analysis` を `enqueue_job`（`job_orchestrator.py`）で enqueue し、`{job_id, status:"QUEUED"}` を返す。
  payload は 029 の `kc_analysis` request スキーマに合わせる（owner/repo/branch + 方式 B の `installation_id` 等）。
  `installation_id` は `InstallationIdDep`（`github.py:133`）で解決（方式 B：秘密はキューに載せない）。
- ポーリングは既存 `GET /api/v1/jobs/{job_id}`（`jobs.py`、`JobRead`）をそのまま使う。本 issue 専用のジョブ受信
  エンドポイントは設けない（service が Cloud SQL に直書きする 018 規約）。

> `analyze-galaxy` は 029 の `kc_analysis` パイプラインを **起動するだけ**。KC 算出・`file_kc`/`dependency` の
> upsert は 029 の `process` が行う。本 issue で新パイプラインや新 JobType は追加しない。

### developer（current_user ↔ GitHub login）解決

`personalGalaxy.developer` は文字列（mock では `"you"`）。KC(file,dev) は GitHub author 単位のため、
current_user → GitHub login の突合が要る。**既存の `resolve_installation_id`（`github.py`）が
current_user の GitHub OAuth トークンから `github_login` を解決している経路**（`user_resp.json()["login"]`）を
参照し、その login を 029 の `file_kc.dev_id` の識別子（027 が確定する users.id か GitHub login か）に突合する。
**dev 識別子の正規形は 027/029 が所有**するため、本 issue はそのマッピングユーティリティを呼ぶに留める
（独自の突合規則を捏造しない）。

## パイプライン・非同期

- **本 issue で service パイプラインは追加しない。** KC 算出パイプライン（`kc_analysis`）・`JobType.kc_analysis`・
  request/result スキーマ・`registry.py` 登録は **029 が所有**（`service/service/registry.py:15` の `PIPELINES` に
  029 が三つ組を追加済みであることを前提とする）。
- `POST .../analyze-galaxy` は `stack.py:105` の `analyze_stack` を雛形に、`enqueue_job` で 029 の `kc_analysis` を
  enqueue するだけ（`JobType.STACK_ANALYSIS` を `JobType.kc_analysis` に差し替える形）。
- 定期スキャン（project 巡回で `kc_analysis` を自動 enqueue し最新 run を更新）は Cloud Functions /
  Cloud Scheduler / Pub-Sub で行う（CLAUDE.md「非同期ジョブ = Cloud Functions（定期スキャン・Pub/Sub トリガー）」）。
  これは issue 037 の責務であり、本 issue は手動トリガ（`POST .../analyze-galaxy`）の配線のみ。

## タスク

### shared

- [ ] 本 issue では shared に新規 ORM/スキーマを追加しない（`file_kc` / `dependency` は 029、`analysis_run` /
      `repo_file` は 026 が所有）。前提 issue が `shared/shared/models/__init__.py:1-6` に `app→shared` 順で
      re-export 済みであることを確認するのみ。

### api（`backend/api/app/api/v1/`）

- [ ] `galaxy.py` を新設し `APIRouter(tags=["Galaxy"])` を定義する（`stack.py:28` を雛形に）。
- [ ] レスポンス用の素の `BaseModel`（snake_case）を定義する：`FileMasteryOut` / `StarSystemOut` /
      `WormholeOut` / `PersonalGalaxyOut`。`personalGalaxySchema`（`schemas.ts:309`）に各フィールド名・型を一致させる
      （`stack.py:57` の `TechStackOut` と同様、`SharedBaseModel` は使わない）。`from` は `alias="from"` で対応。
- [ ] `GET /orgs/{slug}/projects/{project_slug}/galaxy` を実装する：`OrgScope`（`deps.py:64`）で認可 →
      最新の完了 `analysis_run`（029 の `kind=kc_analysis`）を解決 → `file_kc` / `dependency`（029）を `run_id` で取得 →
      module 単位に集計（星系 KC = KC(file) 平均、`schemas.ts:305`）→ `PersonalGalaxyOut` を返す。run 無しは
      `observed=false` で `200`。`SASessionDep`（`deps.py:18`）の DI param 順序を保持する。
- [ ] developer 解決：`resolve_installation_id`（`github.py`）の GitHub login 解決経路を参照し、027/029 の
      dev 識別子マッピングユーティリティで `file_kc.dev_id` に突合する（KC(file,dev) 抽出）。
- [ ] `POST /orgs/{slug}/projects/{project_slug}/analyze-galaxy` を実装する：`stack.py:105` の `analyze_stack` を
      雛形に、`InstallationIdDep`（`github.py:133`）+ `enqueue_job`（`job_orchestrator.py`）で 029 の
      `JobType.kc_analysis` を enqueue し、`JobEnqueuedOut`（`schemas/job.py`）で `202` を返す。
- [ ] `backend/api/app/api/v1/router.py:9,19` に倣い `galaxy_router` を import して `api_router.include_router(galaxy_router)` を追加する。

### service

- [ ] 本 issue では service に変更を加えない（`kc_analysis` パイプラインは 029 が `service/service/pipelines/`・
      `service/service/registry.py:15` に追加済み）。`analyze-galaxy` はそれを enqueue するだけ。

### frontend（`frontend/src/lib/`）

- [ ] `api/client.ts` に `getGalaxy(orgSlug, projectSlug): Promise<PersonalGalaxy>` を新設する
      （`listProjects`（`client.ts:154`）/ `getStack`（`client.ts:271`）の `apiFetch` + Zod parse 規約に倣い、
      `GET /api/v1/orgs/${orgSlug}/projects/${projectSlug}/galaxy` を叩き `personalGalaxySchema.parse(...)`）。
- [ ] `api/client.ts` に `analyzeGalaxy(orgSlug, projectSlug): Promise<AnalyzeStackJob 相当>` を新設する
      （`analyzeStack`（`client.ts:257`）に倣い `POST .../analyze-galaxy` → `analyzeStackJobSchema`（= `{job_id,status}`）を再利用）。
- [ ] `stores/galaxy-store.svelte.ts:16` の `loadMock()` を実 API へ差し替える：`getGalaxy` で取得した
      `PersonalGalaxy` を `galaxy` state に代入（`observed` はレスポンス値をそのまま使う）。
      「最初のスキャンを実行」CTA（009:96, `coming-soon-placeholder.svelte`）から `analyzeGalaxy` + `getJob` ポーリング
      → 完了後 `getGalaxy` 再取得、の経路を配線する。モック直読み（`mockGalaxy` import）を撤去する。
- [ ] `routes/[org]/[project]/galaxy/+page.svelte`（実ルート形は 009 のルート + projects スコープに合わせる）で
      store の実 API 経路を使うよう更新する。`myKc`（`galaxy-store.svelte.ts:13`）の pill 配線は維持。

### infra

- [ ] 本 issue ではインフラ変更なし（定期スキャンの Cloud Functions / Scheduler は issue 037 が担当）。
      手動 enqueue は既存 Cloud Tasks 経路（issue 017）に乗る。

### test

- [ ] api（`backend/api/tests/`）：`GET .../galaxy` が `file_kc` / `dependency` のシードから `personalGalaxySchema`
      互換の JSON（snake_case、`from`/`to` キー、module 集計 KC = 平均）を返すこと。run 無しで `observed=false` を返すこと。
      `mastery=="star"` → `mastered=true` の簡易認定が反映されること。
- [ ] api：`POST .../analyze-galaxy` が `202` + `job_id` を返し、`Job` が `QUEUED`（`JobType.kc_analysis`）で作成され、
      `MockTaskDispatcher.dispatch` がモックで 1 回呼ばれること（`stack.py` の analyze-stack テストと同型）。
- [ ] api：`OrgScope` 認可（非メンバーは 403、org/project なしは 404）。
- [ ] frontend（`frontend/src/lib/`）：`galaxy-store` のユニットテスト（`getGalaxy` で observed/systems が
      state に載ること、`analyzeGalaxy`→ポーリング→再取得の遷移、API モック）。`personalGalaxySchema.parse` が
      実 API 形をパスすること。

## 完了条件

- `GET /api/v1/orgs/{slug}/projects/{project_slug}/galaxy` が、029 が永続化した `file_kc` / `dependency` から
  **`personalGalaxySchema` 互換（snake_case）の `PersonalGalaxyOut` を配信**し、module 単位の星系集計
  （星系 KC = KC(file) 平均）と 029 閾値による mastery 投影、`mastery=="star"` の簡易 mastered 認定が反映される。
- 完了した `kc_analysis` run が無い場合は `observed=false`・`systems=[]`・`wormholes=[]` で `200` を返し、
  フロントが `ComingSoonPlaceholder` を表示できる。
- `POST .../analyze-galaxy` が `202 {job_id}` を返し、029 の `kc_analysis` Job が enqueue され、
  既存 `GET /jobs/{id}` でポーリングできる（api はエージェントを直接実行しない）。
- フロント `client.ts` に `getGalaxy` / `analyzeGalaxy` が追加され、`galaxy-store.loadMock()` のモック直読みが
  実 API 経路に置き換わる（`mockGalaxy` への依存が描画系から消える）。
- バックエンド：`cd backend && uv run ruff check shared/shared api/app service/service && uv run ruff format --check ...` /
  `uv run ty check ...` / `uv run --directory api pytest` が通る。
- フロント：`cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語、Keep a Changelog）に `Added`（Galaxy 個人 KC マップ配信 API・analyze-galaxy enqueue）を追記。

## 対象外・保留

- **KC 算出式・KC(file,dev) の保持・mastery 閾値の確定**（029 が所有）。本 issue は集計・投影・配信のみ。
- **quiz 連動の `mastered` 実認定**（034 依存）。本 issue は `mastery=="star"` の簡易認定に留める（009:87・009:396）。
- **dev 識別子（users.id か GitHub login か）の正規形確定**（027/029 が所有）。本 issue はマッピングユーティリティを呼ぶのみ。
- **依存グラフ（wormhole）抽出ロジック**（029/027 が所有）。本 issue は `dependency` テーブルを読むだけ。
- **定期スキャン（Cloud Functions / Scheduler / Pub-Sub）による自動 run 更新**（037）。
- **3D（Three.js / WebGL）UI**（009 §10.2 で Future、別ドメイン UI）。
- pgvector による概念マッピング/類似検索（将来拡張、026 で拡張有効化のみ）。

## 参考

- 関連 issue
  - `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc` / `dependency` ORM・`kc_analysis` パイプライン・KC→mastery 閾値（前提・データ供給元）
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file` 共有テーブル・File 同一性方針
  - `docs/issue/027-backend-github-history-client-extension.md` — authorship / GitHub login ↔ users.id 突合ユーティリティ・依存抽出
  - `docs/issue/009-knowledge-galaxy-2d-map.md` — Galaxy 個人ビューのメタファー・スキーマ・MVP/Future 線引き（§390-398）
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 202 enqueue + `GET /jobs/{id}` ポーリング契約（雛形）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — 同じ集計/配信 api 層パターン（Overview/Matrix）
  - `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — quiz 連動 mastered 実認定（後続）
  - `docs/issue/037-backend-periodic-scan-cloud-functions.md` — 定期スキャンによる run 更新（後続）
- フロント契約（差し替え対象）
  - `frontend/src/lib/api/schemas.ts:285-321` — `masteryStatusSchema` / `fileMasterySchema` / `wormholeSchema` / `starSystemSchema` / `personalGalaxySchema`
  - `frontend/src/lib/mocks/galaxy.ts:5` — `mockGalaxy`（差し替えで描画系から撤去）
  - `frontend/src/lib/stores/galaxy-store.svelte.ts:13,16` — `myKc` / `loadMock()`（実 API へ差し替え）
  - `frontend/src/lib/api/client.ts:154,257,271` — `listProjects` / `analyzeStack` / `getStack`（`getGalaxy` / `analyzeGalaxy` の踏襲元）
- 既存 backend（雛形）
  - `backend/api/app/api/v1/stack.py:57,105,146` — `TechStackOut`（素の BaseModel snake_case）/ `analyze_stack`（202 enqueue）/ `get_stack`
  - `backend/api/app/api/v1/projects.py:18-169` — `/orgs/{slug}/projects/{project_slug}` スコープ・`OrgScope` 認可
  - `backend/api/app/api/v1/github.py:133` — `resolve_installation_id` / `InstallationIdDep`（GitHub login 解決・方式 B）
  - `backend/api/app/api/deps.py:18,64` — `SASessionDep` / `OrgScope`（Annotated DI param 順序厳守）
  - `backend/api/app/services/job_orchestrator.py` — `enqueue_job`
  - `backend/api/app/schemas/job.py` — `JobEnqueuedOut` / `JobRead`
  - `backend/api/app/api/v1/router.py:9,19` — ルーター include 追加点
  - `backend/shared/shared/enums.py:11` — `JobType`（029 が `kc_analysis` を追加）
  - `backend/service/service/registry.py:15` — `PIPELINES`（029 が `kc_analysis` 三つ組を追加）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — snake_case 配信（素の BaseModel）、Annotated DI param 順序厳守、
    PATCH 規約、Secret Manager / 方式 B、Vertex AI + ADC、router 登録、ゲート（ruff/ty/pytest, bun check/lint/test:unit）、
    `CHANGELOG.md`（日本語）
