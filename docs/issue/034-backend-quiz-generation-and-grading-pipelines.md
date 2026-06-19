# クイズ生成・採点パイプラインと配信/途中保存 API を実装する

## 概要

フロントの返済体験（Re:Pay / クイズ）は現在すべてモックで動いている。`frontend/src/lib/api/client.ts`
の `listQuizzes`（`client.ts:350`）/ `getQuizSession`（`client.ts:355`）/ `saveQuizAnswer`（`client.ts:361`）/
`submitQuiz`（`client.ts:366`）は `frontend/src/lib/api/quiz-mock.ts` を返すだけで、バックエンド実体が無い。

本 issue は **返済体験の縦切り**として裏側を実装する。issue 018（スタック解析の非同期化）で確立した
「api は enqueue + 配信/ポーリングに徹し、重い処理（GitHub 取得・Gemini 推論）は service の非同期
パイプラインに載せる」パターンをそのまま踏襲し、

1. `shared` に `quiz_session` / `quiz_answer` / `quiz_result` の ORM を新設（api が Alembic 0007+ で作成）。
2. `JobType` に `quiz_generation` / `quiz_grading` を追加し、service に 2 本のパイプラインを登録。
   - `quiz_generation`: `GitHubGitClient` でファイル内容取得 → Gemini（Vertex AI + ADC）で L1-L5 の 5 問 +
     正答/採点基準を生成（`response_mime_type=application/json`）→ `quiz_session.questions` 保存。
   - `quiz_grading`: 回答 + 正答 + コード文脈を Gemini で意味採点 → `understood` / `gap_concepts`（仕様書 §5.3）
     → `kc_before` → `kc_after` を**暫定**算出 → `certified_via="quiz"` で file_kc（issue 029）へ反映する**フック**。
3. api（`/orgs/{slug}/projects/{project_slug}/...` 配下）に一覧/生成/取得/途中保存/採点/結果の 6 エンドポイントを追加。
4. フロント `client.ts` の 4 つのモック関数を実 API に差し替える。`submit` を **202 化**するため、
   現状同期 mock の `submitQuiz` の契約が変わる（後述、フロント連携を明示）。

レスポンスはすべて **snake_case 維持**（`schemas.ts:323-378` の Quiz スキーマに一致させる。
issue 018 の `TechStackOut` と同様、素の `BaseModel` で snake_case を返す）。`developer_id` は
`current_user.id` に束ね、他人のセッションへのアクセスを認可で遮断する。

> KC の**本算出**は issue 029（KC パイプライン）が所有する。本 issue の `kc_before` / `kc_after` は
> 採点パイプライン内の**暫定値**にとどめ、確定式は 029 へ委譲する（捏造しない）。学習プラン生成は
> issue 035 が所有し、本 issue は `quiz_result.learning_plan_id` の紐付けと enqueue 連携のみ行う。

## 背景・目的

### 現状（フロントのみ・モック）

- `quiz-mock.ts` に `SESSIONS`（`quiz-user-service` / `quiz-token-rotation`、各 5 問 L1-L5、MC は `choices[]`、
  free_text は `code_snippet` 有無混在）、`RESULT`（`kc_before: 0.23` → `kc_after: 0.47`、`learning_plan_id: "plan-001"`）、
  `QUIZ_LIST`（2 件、`reason` / `question_count` / `estimated_minutes`）が定義されている（`quiz-mock.ts:19-185`）。
- `developer_id: "you"`、`repo_full_name: "demo/app"` 固定。
- `submitQuiz` は同期で `QuizResult` を即返す mock（`client.ts:366-369`）。`saveQuizAnswer` は「PATCH 想定」の
  コメント付きで楽観的に返すだけ（`client.ts:361-364`）。
- 仕様書 §6.4「クイズ UI」を実装したフロント issue は `docs/issue/010-quiz-repayment-experience.md`。
  010 は「本 issue では実採点・実 API・実 KC 算出を実装しない」と明記（=今回作る対象）。

### 目的

1. クイズの **生成**（低 KC ファイルのコード → 設問）と **採点**（意味採点 → 理解/ギャップ抽出）を
   service の非同期パイプラインに載せ、api リクエスト外で実行する。
2. api を「セッション CRUD + 生成/採点の enqueue + 結果配信」に薄くし、ポーリングは既存 `GET /jobs/{id}`
   （`jobs.py`）を併用する。
3. 途中保存（`saveQuizAnswer`）を PATCH の upsert として実 DB に永続化する。
4. フロント `client.ts` の 4 モック関数を実 API へ差し替える（`submit` の 202 化に伴う契約変更を明示）。

### 前提 issue（depends_on）

- **issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file`
  の共有テーブル土台、`shared` への ORM 追加規約、`models/__init__.py` の import 順（app→shared）、
  Alembic 0006 と pgvector 拡張。本 issue の quiz テーブルは同じ shared ORM 規約・連番系列（0007 以降）に乗る。
- **issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc`（`certified_via[quiz/authorship/review]`）
  と KC 算出パイプライン。本 issue の `quiz_grading` は採点後に `certified_via="quiz"` で file_kc へ反映する
  **フック**を呼ぶ（KC の確定式・反映ロジックの本体は 029 が所有）。`kc_before` / `kc_after` は本 issue では暫定。

## データモデル

すべて `shared/shared/models/` に新設（雛形 `shared/shared/models/tech_stack.py`: `uuid4` PK・JSON 列・
`DateTime(timezone=True)`・`UniqueConstraint`）。`shared/shared/models/__init__.py:1-6` に import 順 app→shared で
re-export を追記。Alembic マイグレーションは **api が所有**（連番は `0001`-`0005` 使用済み、026 が `0006` を取るため
本 issue は **`0007`** 以降。雛形 `api/app/alembic/versions/0003_add_tech_stacks.py` / `0005_add_jobs.py`）。service は
DML のみ。

### 新規テーブル `quiz_sessions`（shared）

`schemas.ts:341-351` `quizSessionSchema` に対応。

| 列 | 型 / 備考 |
|---|---|
| `id` | `uuid4` PK（`schemas.ts:342` `id`） |
| `project_id` | `uuid`（FK は付けず nullable 可。`Job.project_id` の前例に倣う。スコープ解決は projects.py 配下のルートで実施） |
| `developer_id` | `uuid` = `users.id`（`schemas.ts:343` `developer_id`。認可で `current_user.id` に束ねる） |
| `file_path` | `str`（`schemas.ts:344` `file.path`） |
| `repo_full_name` | `str`（`schemas.ts:344` `file.repo_full_name`） |
| `status` | `str` enum `not_started` / `in_progress` / `grading` / `completed`（`schemas.ts:347`。**小文字**。Job の `JobStatus` 大文字とは別系列） |
| `score` | `float \| None`（`schemas.ts:350`） |
| `started_at` / `completed_at` | `datetime \| None`（`schemas.ts:348-349`、`DateTime(timezone=True)`） |
| `questions` | `list` JSON 列（生成済み `quizQuestion` 配列。`schemas.ts:326-333` の形＝`id`/`kind`/`prompt`/`code_snippet`/`choices?`/`difficulty`。正答/採点基準は配信に載せないため別 JSON または `questions` 内の非公開フィールドとして保持し、配信時に除去） |
| `source_kc` | `float \| None`（受験対象選定時の KC スナップショット。配信スキーマには無いので内部用） |

> `file`（`{path, repo_full_name}`）は配信時に `file_path` / `repo_full_name` から組み立てる。
> `answers` は配信時に `quiz_answers` から join して埋める（`schemas.ts:346`）。

### 新規テーブル `quiz_answers`（shared）— 途中保存 upsert

`schemas.ts:335-339` `quizAnswerSchema` に対応。1 設問 1 行。

| 列 | 型 / 備考 |
|---|---|
| `id` | `uuid4` PK |
| `session_id` | `uuid` FK → `quiz_sessions.id` |
| `question_id` | `str`（`schemas.ts:336`） |
| `value` | `str`（`schemas.ts:337`。MC は choice id、free_text は本文） |
| `saved_at` | `datetime`（`schemas.ts:338`、`DateTime(timezone=True)`） |

`UniqueConstraint("session_id", "question_id", name="uq_quiz_answers_session_question")` で upsert キーにする
（PATCH 途中保存。`stack_analysis.py` の `pg_insert(...).on_conflict_do_update(...)` パターンに倣う）。

### 新規テーブル `quiz_results`（shared）

`schemas.ts:353-360` `quizResultSchema` に対応。1 セッション 1 行。

| 列 | 型 / 備考 |
|---|---|
| `id` | `uuid4` PK |
| `session_id` | `uuid` FK → `quiz_sessions.id`（`schemas.ts:354`、配信時は `session_id`） |
| `understood` | `list` JSON（`Concept[]` = `{id,label}`。`schemas.ts:355`） |
| `gap_concepts` | `list` JSON（`Concept[]`。`schemas.ts:356`。issue 035 の学習プラン入力。035 で `string[]` へ正規化変換） |
| `kc_before` | `float`（`schemas.ts:357`。**暫定値**、本算出は 029） |
| `kc_after` | `float`（`schemas.ts:358`。**暫定値**） |
| `learning_plan_id` | `uuid \| None`（`schemas.ts:359`。035 が発番、本 issue は紐付けのみ） |

## API

すべて projects スコープ（`projects.py:18-169` の `/orgs/{slug}/projects/{project_slug}/...` 形）に揃える。
認可は `OrgScope`（`deps.py:64`）でメンバーシップを強制し、さらに `quiz_session.developer_id == current_user.id`
を**ハンドラ内で検証**して他人のセッションを遮断（403）。`router.py` に `quizzes_router` を新規 include。
**Annotated DI param 順序を変更しない**（`deps.py` 規約）。

| メソッド・パス | レスポンス / 一致スキーマ | 備考 |
|---|---|---|
| `GET .../quizzes` | `QuizList`（`schemas.ts:362-370` `quizListSchema`）。`{ quizzes: QuizListItem[] }` | `listQuizzes` 差し替え先。`reason` は受験対象の KC 低下理由（029/030 由来。未配線時は固定文言可） |
| `POST .../quizzes/generate` | `202 {job_id, status}`（`JobEnqueuedOut`、`schemas.ts:157` `analyzeStackJobSchema` 形） | `JobType.QUIZ_GENERATION` を enqueue。body に対象 `file_path`（と `branch`）。生成完了で `quiz_session` 行が立つ |
| `GET .../quizzes/{session_id}` | `QuizSession`（`schemas.ts:341-351` `quizSessionSchema`） | `getQuizSession` 差し替え先。`questions` は正答/採点基準を**除去して**配信。`answers` は join |
| `PATCH .../quizzes/{session_id}/answers` | `QuizAnswer`（`schemas.ts:335-339` `quizAnswerSchema`） | `saveQuizAnswer` 差し替え先。upsert。副作用で `status` を `in_progress` / `started_at` を初回設定 |
| `POST .../quizzes/{session_id}/submit` | `202 {job_id, status}`（`JobEnqueuedOut`） | `JobType.QUIZ_GRADING` を enqueue し `quiz_session.status="grading"` に遷移。**契約変更**（後述） |
| `GET .../quizzes/{session_id}/result` | `QuizResult`（`schemas.ts:353-360` `quizResultSchema`）。未採点は 404 | `submit` の 202 化に伴い、結果はここから取得 |

### `submit` の 202 化に伴うフロント契約変更（連携明示）

現状 `submitQuiz(sessionId): Promise<QuizResult>` は同期で結果を返す（`client.ts:366`）。本 issue では
採点を非同期化するため、`submit` は **`202 {job_id}` を返し、`GET /jobs/{id}`（`jobs.py`）でポーリング →
`status==="COMPLETED"` 後に `GET .../quizzes/{session_id}/result` で `QuizResult` を取得**する 2 段に変わる。
issue 018 の `analyzeStack` → `getJob` → `getStack` と同型。`client.ts` / `quiz-store.svelte.ts` の改修が必要。

> `jobs.py:72` は `STACK_ANALYSIS` のみ `agent_trace` / `tech_stack` を持ち上げている。`QUIZ_GRADING` Job でも
> 進捗を返したい場合は同様の分岐追加を検討するが、結果本体は `GET .../quizzes/{session_id}/result` から読む
> （`get_job` は creator スコープ＝`developer_id` 本人のみ通る点が認可上も整合）。

## パイプライン・非同期

issue 018 の三つ組規約（`(RequestSchema, ResultSchema, process)`）に従う。

### JobType 追加（`shared/shared/enums.py:11-16`）

```python
QUIZ_GENERATION = "quiz_generation"   # quiz-generation
QUIZ_GRADING = "quiz_grading"         # quiz-grading
```

値は lowercase snake_case（enqueue 時に `_`→`-` でタスクパス名 `quiz-generation` / `quiz-grading` になる）。

### request / result スキーマ（`shared/shared/schemas/quiz.py` 新設）

`shared/shared/schemas/stack_analysis.py` に倣い `JobRequestBase` / `JobResultBase` を継承、`GitHubRef`
（`installation_id` のみ＝**方式 B**）を再利用。

- `QuizGenerationRequest`: `session_id` / `project_id` / `file_path` / `repo_full_name` / `branch` / `github: GitHubRef`
  / `requested_by`。
- `QuizGenerationResult`: `session_id` / `status` / `question_count` / `agent_trace`。
- `QuizGradingRequest`: `session_id` / `project_id` / `github: GitHubRef` / `requested_by`。
- `QuizGradingResult`: `session_id` / `status` / `score` / `kc_before` / `kc_after` / `agent_trace`。

### service パイプライン（`service/service/pipelines/`、`service/service/registry.py:15` に登録）

`stack_analysis.py` の `process(request, ctx)` を雛形にし、`ctx.session` で DML、`run_task` が冪等に
`Job.result_data` を書く。GitHub は `GitHubGitClient.get_file_content`（`github_git_client.py:164`）で内容取得、
トークンは `GitHubAppService`（方式 B、Secret Manager から mint）。Gemini は `gemini_stack_service` の
Vertex AI + ADC（`stack_analysis.py:44` `_vertex_model_name`、`response_mime_type="application/json"`）。

- `quiz_generation.process`: `file_path` の内容取得 → Gemini で L1-L5 の 5 問（`multiple_choice` / `free_text` 混在、
  該当箇所に `code_snippet` を添付）+ 各問の正答/採点基準を生成 → `quiz_session.questions`（正答/基準は非公開フィールド）
  と `status="not_started"`、`source_kc` を upsert。
- `quiz_grading.process`: `quiz_answers` + 非公開の正答/基準 + コード文脈を Gemini で意味採点（free_text は
  非決定的なので冪等性に注意。`run_task` は冪等だが、`status==COMPLETED`/`completed` で再採点をスキップ）→
  `understood` / `gap_concepts`（仕様書 §5.3）抽出 → `score` / `kc_before` / `kc_after`（**暫定**）算出 →
  `quiz_results` upsert、`quiz_session.status="completed"` / `completed_at` 設定 → `certified_via="quiz"` で
  file_kc（029）反映フック呼び出し → 学習プラン生成（035 へ enqueue）連携の余地（本 issue は紐付けのみ）。

### 定期スキャン

本 issue の生成/採点はユーザー操作起点（手動トリガ）。定期スキャン（Cloud Functions / Pub-Sub）は対象外
（受験対象の自動選定は 029/030 の KC・負債検知側、定期化は issue 037）。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `shared/shared/models/quiz_session.py` / `quiz_answer.py` / `quiz_result.py` を新設（雛形 `models/tech_stack.py`）。
      `quiz_answers` に `UniqueConstraint("session_id","question_id")`。
- [ ] `shared/shared/models/__init__.py:1-6` に 3 モデルを import 順 app→shared で re-export 追記。
- [ ] `shared/shared/enums.py:16` の `JobType` に `QUIZ_GENERATION` / `QUIZ_GRADING` を追加。
- [ ] `shared/shared/schemas/quiz.py` を新設（`schemas/stack_analysis.py` の `JobRequestBase`/`JobResultBase`/`GitHubRef` 流用）。

### api（`backend/api/app/`）

- [ ] `api/app/alembic/versions/0007_add_quiz_tables.py` を新設（雛形 `0005_add_jobs.py`。`down_revision` は 026 の `0006`）。
- [ ] `api/app/api/v1/quizzes.py` を新設し上記 6 エンドポイントを実装（`stack.py:105` の enqueue 雛形 / `projects.py` の
      `OrgScope` ルート形 / PATCH 部分更新）。`developer_id == current_user.id` をハンドラで検証。
- [ ] レスポンスは素の `BaseModel` で snake_case（`stack.py:57` `TechStackOut` パターン）。`quizSessionSchema` /
      `quizResultSchema` / `quizAnswerSchema` / `quizListSchema` に一致させる。
- [ ] `api/app/api/v1/router.py` に `quizzes_router` を import & include。
- [ ] enqueue は `job_orchestrator.enqueue_job`（`stack.py:135`）、`installation_id` は `InstallationIdDep`
      （`github.py:133`）で方式 B 搬送。

### service（`backend/service/service/`）

- [ ] `service/service/pipelines/quiz_generation.py` / `quiz_grading.py` を新設（`pipelines/stack_analysis.py` 雛形、
      `process(request, ctx)`）。
- [ ] `service/service/registry.py:15` の `PIPELINES` に 2 つの三つ組を登録。
- [ ] Gemini 呼び出しは `services/gemini_stack_service.py` の Vertex AI + ADC を流用拡張（`response_mime_type="application/json"`、
      `_vertex_model_name` 方式）。GitHub は `services/github_git_client.py:164` `get_file_content` + 方式 B の token mint。
- [ ] `quiz_grading` で `certified_via="quiz"` の file_kc 反映フックを呼ぶ（実体は issue 029、本 issue は呼び出し配線のみ）。

### frontend（`frontend/src/lib/`）

- [ ] `client.ts:350` `listQuizzes` を `GET /api/v1/orgs/{slug}/projects/{project_slug}/quizzes` に差し替え。
- [ ] `client.ts:355` `getQuizSession` を `GET .../quizzes/{session_id}` に差し替え。
- [ ] `client.ts:361` `saveQuizAnswer` を `PATCH .../quizzes/{session_id}/answers` に差し替え（upsert）。
- [ ] `client.ts:366` `submitQuiz` を **`202 {job_id}` 返却 → `getJob` ポーリング → `GET .../quizzes/{session_id}/result`**
      の 2 段へ変更（契約変更）。`generateQuiz`（`POST .../quizzes/generate` → 202）を新設。
- [ ] `frontend/src/lib/stores/quiz-store.svelte.ts` を採点ポーリング対応に改修（issue 018 の
      `stack-analysis-store` のポーリング型を参照）。`quiz-mock.ts` 直読みを撤去。

### infra

- [ ] 追加インフラ無し（既存 Cloud Tasks キュー / service Cloud Run / Secret Manager / Vertex AI を流用）。
      service runtime SA の `roles/aiplatform.user`・Secret Manager 参照は issue 017/018 で配線済み前提。

### test

- [ ] api（`backend/api/tests/`）: `POST .../quizzes/generate` / `.../submit` が `202` + `job_id` を返し `Job` が `QUEUED`、
      `MockTaskDispatcher.dispatch` が 1 回呼ばれること。`PATCH .../answers` の upsert（同一 question 2 回で 1 行）。
      他人の `developer_id` セッションが 403 になること。`GET .../quizzes` / `{id}` / `result` の形が Zod 一致。
- [ ] service（`backend/service/tests/`）: `quiz_generation.process` が `GitHubGitClient` / Gemini モックで
      `quiz_sessions.questions` を upsert すること。`quiz_grading.process` が `quiz_results` を書き `status=completed`、
      再配送（at-least-once）で二重採点しない冪等性。方式 B で token を mint する経路。
- [ ] frontend（`frontend/`）: `quiz-store` のユニットテスト（生成 enqueue → ポーリング → result 取得 / 途中保存）。

## 完了条件

- フロントの一覧/受験/途中保存/採点が **実 API** で動く（`quiz-mock.ts` 直読みが撤去され `client.ts` の 4 関数が実 API 化）。
- `POST .../quizzes/generate` / `.../submit` が `202 {job_id}` を返し、service が api リクエスト外で生成/採点を実行、
  結果を Cloud SQL（`quiz_sessions` / `quiz_results`）へ直接書き込む（api への結果コールバック・Pub/Sub publish が無い）。
- `PATCH .../quizzes/{session_id}/answers` が upsert で途中保存され、再保存で行が増えない。
- 他人の `developer_id` セッションへのアクセスが 403 で遮断される。
- GitHub トークンが方式 B（`installation_id` のみ搬送、service が Secret Manager から mint）で、キュー/GCS に平文の秘密が残らない。
- バックエンド: `cd backend && uv run ruff check shared/shared api/app service/service && uv run ruff format --check ...`
  / `uv run ty check ...` / `uv run --directory api pytest`（shared / service も）が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Added`（クイズ生成・採点パイプライン + 配信/途中保存 API）/ `Changed`（`submitQuiz` を非同期化）を追記。

## 対象外・保留

- **KC の本算出**（`kc_before` / `kc_after` の確定式・file_kc への正式反映）は issue 029 が所有。本 issue は暫定値 + 反映フックのみ。
- **学習プラン生成**は issue 035 が所有。本 issue は `quiz_result.learning_plan_id` 紐付け / enqueue 連携のみ。
- **受験対象の自動選定**（低 KC ファイル抽出）は 029/030 の KC・負債検知に依存。本 issue は `file_path` 指定で生成可能とする。
- **gap_concepts の型正規化**（`Concept[]` → `string[]`）は学習プラン保存側（035）で実施。
- 定期スキャン（Cloud Functions / Pub-Sub）は issue 037。pgvector による概念マッピング/重複抑制は将来拡張。

## 参考

- 関連 issue
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 非同期パイプライン（enqueue + 202 + ポーリング）の雛形（本 issue の様式・実装パターン元）
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — shared テーブル土台 / Alembic 0006 / models import 順（前提）
  - `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — KC 算出・`file_kc`・`certified_via`（前提、採点後フックの委譲先）
  - `docs/issue/010-quiz-repayment-experience.md` — フロント実装（§6.4 クイズ UI / §5.3 ギャップ抽出 / `kc_before`→`kc_after`）
  - `docs/issue/035-backend-learning-plan-generation-and-api.md` — 学習プラン生成（`gap_concepts` を入力に、enqueue 連携先）
- フロント契約 / モック
  - `frontend/src/lib/api/schemas.ts:323-378` — `quizQuestionSchema` / `quizAnswerSchema` / `quizSessionSchema` /
    `quizResultSchema` / `quizListItemSchema` / `quizListSchema`（配信が一致すべき正）
  - `frontend/src/lib/api/quiz-mock.ts` — `SESSIONS` / `RESULT` / `QUIZ_LIST`（差し替え対象）
  - `frontend/src/lib/api/client.ts:350-369` — `listQuizzes` / `getQuizSession` / `saveQuizAnswer` / `submitQuiz`（実 API 化対象）
- 既存バックエンド（流用・雛形）
  - `backend/api/app/api/v1/stack.py:105` — `analyze_stack`（202 enqueue）/ `:57` `TechStackOut`（snake_case 配信）
  - `backend/api/app/api/v1/projects.py:18-169` — `/orgs/{slug}/projects/{project_slug}` ルート形 / `OrgScope`
  - `backend/api/app/api/v1/jobs.py:47` — `GET /jobs/{id}`（creator スコープのポーリング）
  - `backend/api/app/api/v1/github.py:92` `resolve_installation_id` / `:133` `InstallationIdDep`（方式 B）
  - `backend/service/service/pipelines/stack_analysis.py` — `process(request, ctx)` 雛形 / `:44` `_vertex_model_name`
  - `backend/service/service/registry.py:15` — `PIPELINES` 三つ組登録
  - `backend/service/service/services/github_git_client.py:164` `get_file_content` / `gemini_stack_service.py`（Vertex AI + ADC）
  - `backend/shared/shared/schemas/stack_analysis.py` — `JobRequestBase`/`JobResultBase`/`GitHubRef`（方式 B）流用元
  - `backend/shared/shared/models/tech_stack.py` — ORM 雛形 / `models/__init__.py:1-6` re-export
  - `backend/api/app/alembic/versions/0005_add_jobs.py` — Alembic 雛形（次番 0007）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — Secret Manager 必須 / Vertex AI + ADC（API キー不使用）/ 方式 B /
    Annotated DI param 順序厳守 / `models/__init__.py` import 順（app→shared）/ JobType 追加 / `router.py` 登録 /
    PATCH 部分更新 / snake_case 配信 / CHANGELOG（日本語）/ ゲート（ruff・ty・pytest / bun check・lint・test:unit）
