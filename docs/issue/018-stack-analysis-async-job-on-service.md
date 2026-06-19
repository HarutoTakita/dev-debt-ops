# 重い処理（スタック解析）を service コンテナへ移し非同期ジョブ化する

## 概要

現在 `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack` は、ADK エージェント
（`list_key_files` → `read_file` × N → `classify_stack` → `save_stack`）を **api のリクエスト
ハンドラ内で同期実行** している（`backend/app/api/v1/stack.py` → `app.agent.stack_agent.run_stack_analysis`）。
GitHub API 往復・Gemini（Vertex AI）呼び出しを含むこのループは長時間・高負荷で、api ワーカーを
塞ぎ、Cloud Run のリクエストタイムアウトに抵触し得る。

本 issue は、Issue 015（api/service 分割）と Issue 016（Cloud Tasks の非同期タスク基盤）の
**最初の実体化（ペイオフ）** である。スタック解析の重い処理を **service コンテナ**
（参考実装の `worker` 相当）へ移設し、api は **Cloud Tasks 経由でディスパッチ**するだけにする。
api は Job を作成して `202 {job_id}` を即返し、service が api リクエスト外でエージェントを実行して
`TechStack` を永続化、**同じトランザクションで `Job` 行を `COMPLETED` + 結果へ Cloud SQL に直接書き込む**
（api へのコールバックも Pub/Sub publish も無い）。フロントは「同期レスポンス」から
「enqueue + `GET /jobs/{id}` ポーリング」へ切り替え、`agent_trace` を進捗 UI に流す。

> Job のステータス値は Issue 016 の `JobStatus`（`StrEnum`、`QUEUED` / `PROCESSING` / `COMPLETED` / `FAILED` / `CANCELLED`、
> `app_ref/services/shared/shared/enums.py` 踏襲の **大文字**）をそのまま使う。本 issue の記述・Zod スキーマ・
> フロントのポーリング判定（`job.status === "COMPLETED"` 等）はすべてこの大文字値に揃える。

`GET /api/v1/github/repositories/{owner}/{repo}/stack`（永続化済み `TechStack` の読み出し）は
**インターフェース不変** とし、解析の完了/未完了に依らず従来どおり利用できる。

## 背景・目的

### 現状（同期・api 内実行）

`backend/app/api/v1/stack.py::analyze_stack` は以下を **1 リクエスト内で同期実行** する：

1. `resolve_github_client`（`backend/app/api/v1/github.py`）が、ユーザーの GitHub OAuth から
   GitHub App installation token を mint して `GitHubGitClient` を yield する。
2. `run_stack_analysis(client, session, owner, repo, branch)`（`backend/app/agent/stack_agent.py`）が
   ADK `Runner` を回し、`list_key_files` → `read_file`（最大 10 ファイル）→ `classify_stack`
   （Gemini/Vertex AI、`backend/app/services/gemini_stack_service.py`）→ `save_stack`（`tech_stacks` upsert）を
   エージェントが自律的に呼ぶ。
3. 永続化された `TechStack` 行を読み直し、`agent_trace` を添えて `TechStackOut` を返す。

問題点：

- **api ワーカーが長時間ブロックされる。** GitHub 往復 + Gemini 推論 + DB I/O を含むループは数秒〜数十秒
  かかり得る。Cloud Run（api）のリクエストタイムアウト・同時実行枠を圧迫し、外部公開サービスの
  応答性とオートスケール効率を悪化させる。
- **失敗時の再試行・観測性が貧弱。** 同期実行のため、途中失敗はそのまま 5xx になり、リトライ/バックオフや
  ジョブ状態の追跡ができない。
- **「重い処理は service で」という分割方針（Issue 015/016）の意図に反する。** 現状はモノリス時代の
  実装が api に残っている。

### 目的

1. スタック解析の重い処理を **service コンテナ**（`backend/service/`）へ移設し、api リクエスト外で実行する。
2. api を「Job 作成 + Cloud Tasks へ enqueue + `202 {job_id}` 返却」に薄くし、`GET /jobs/{id}` で状態と結果
   （`agent_trace` + `TechStack`）を返す。
3. service が処理完了後、**自前の DB セッションで `Job` 行を `COMPLETED`/`FAILED` + `result_data`（`agent_trace`）に直接更新**する
   （api への結果コールバックは無い）。`TechStack` も同じく Cloud SQL に書く。
4. フロントを enqueue + ポーリングに変更し、`agent_trace` を用いた進捗 UI を提供する。
5. `GET .../stack` は不変のまま、永続化済み `TechStack` を返し続ける。

### 前提 Issue（depends_on）

- **Issue 015** `docs/issue/015-backend-api-service-split-monorepo.md` — `backend/` を uv workspace 化し
  `shared` / `api` / `service` に分割する基盤。本 issue は `backend/service/` と `backend/shared/` の存在を前提とする。
- **Issue 016** `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks（request ディスパッチ）
  + Job ライフサイクル + GCS スピルオーバー + ローカル mock/エミュレータの基盤。本 issue は `shared` の `Job` モデル、
  enqueue オーケストレータ（`job_orchestrator.enqueue_job`）と dispatcher Protocol（`TaskDispatcher.dispatch`）、
  service 側の `/tasks/{pipeline}` ルーティング、service が結果を Cloud SQL に直接書き戻す規約、mock-worker を
  そのまま利用する。結果通知に Pub/Sub やコールバックは使わない（service が DB に直接書く）。

> 本 issue は新しいキュー基盤を作らない。**既に 016 で用意された基盤に「stack-analysis」という最初の
> 実パイプラインを載せる** ことが主眼である。

### 独自性（他 Issue との差分）

Issue 016 は「ダミー/サンプルパイプラインで配線を通す」ところまで。本 issue は **既存の実機能
（ADK スタック解析）を非同期化する最初の移植** であり、(a) ADK エージェント + Vertex AI + GitHub
トークンという「現実の重い依存」を service 側へ持ち込む、(b) ペイロードに GitHub の秘密が乗る懸念への
具体的な緩和策を決める、(c) フロントを同期 UI から非同期ポーリング UI へ作り替える、という 3 点で
基盤 issue と性質が異なる。

## タスク

### shared: request/result スキーマを定義（`backend/shared/shared/`）

- [ ] `shared/shared/schemas/stack_analysis.py` を新設し、Pydantic v2 で以下を定義する
      （参考実装 `app_ref/services/shared/shared/schemas/code_to_spec.py` の `SharedBaseModel` 規約に倣う）：

  | スキーマ | フィールド（要点） |
  |---|---|
  | `StackAnalysisRequest` | `job_id: str`、`owner: str`、`repo: str`、`branch: str = "main"`、`github` (= 後述のトークン受け渡し方式に応じた最小情報)、`requested_by: str`（user id） |
  | `StackAnalysisResult` | `job_id: str`、`status: ResultStatus`、`owner` / `repo` / `branch`、`languages: list[TechItem]`、`categories: TechCategories`、`agent_trace: list[str]`、`error: PipelineError \| None`、`timing: PipelineTiming \| None`。**Pub/Sub に publish はせず、service がこのオブジェクトを `Job.result_data`（JSONB）へ直接書き込む際の構造体として使う** |
  | `TechItem` / `TechCategories` | `name` / `confidence("high"|"medium"|"low")`、カテゴリ 9 種（`frameworks` … `other`） — 既存 `backend/app/api/v1/stack.py` の `TechItemOut` / `TechCategoriesOut` を shared へ昇格 |

  > `Job` モデル自体は Issue 016 で `backend/shared/shared/models/job.py` に置かれる（`from shared.models import Job`）。
  > api と service の双方がこの `Job` を import する。`shared` の依存は `pydantic>=2` + `sqlmodel` のみ
  > （github/gemini/httpx/PyJWT は shared に置かない）。Alembic マイグレーションと DB エンジン/セッション生成は **api が所有**
  > （`backend/api/app/core/db.py`）。service は自前の薄い `backend/service/service/db.py`（engine/session）で
  > shared モデルに対し DML するのみ（マイグレーションは実行しない）。

- [ ] `shared/shared/enums.py`（016 で導入）に `stack-analysis` を pipeline 名として追加（`JobType.STACK_ANALYSIS = "stack_analysis"`、
      enqueue 時に `_` → `-` 変換し queue/タスクパス名 `stack-analysis` を作る。参考実装 `workflow_orchestrator._job_type_to_pipeline_name`）。

### service: stack-analysis パイプラインを移設（`backend/service/service/`）

- [ ] `backend/app/agent/stack_agent.py` を `backend/service/service/pipelines/stack_analysis.py` へ移設する
      （`build_tools` / `create_stack_agent` / `run_stack_analysis` を移す）。
- [ ] `backend/app/services/gemini_stack_service.py` を `backend/service/service/services/gemini_stack_service.py` へ移設する。
- [ ] `backend/app/services/github_git_client.py`（および GitHub App トークン mint に必要な
      `backend/app/services/github_app.py`）を **service へ移設**する
      （`backend/service/service/services/`）。これらは `httpx` / `PyJWT` / `cryptography` の重い依存を必要とする
      ため、**`shared` には置かない** — Issue 015 の `shared` は **共有データ層**（`pydantic` + `sqlmodel`、
      `backend/shared/pyproject.toml` の `dependencies = ["pydantic>=2", "sqlmodel"]`。enum・共有スキーマ・共有 ORM モデル）であり、
      統合クライアント（`httpx` / `PyJWT` / `cryptography` を要する GitHub クライアント等）は置かない方針。
      ここに GitHub クライアントを置くと shared の依存が肥大化し api/service 双方へ重い依存が伝播する。
      api は GitHub installation token の mint に既に `github_app` を使うため、api 側は既存の
      `backend/api/app/services/github_app.py` を引き続き保持する（service 側は方式 B のために独自に参照する）。
- [ ] パイプラインの公開関数を統一する：

  ```python
  # backend/service/service/pipelines/stack_analysis.py
  async def process(request: StackAnalysisRequest) -> StackAnalysisResult:
      """ADK エージェントを実行し TechStack を永続化、結果スキーマを返す。"""
  ```

  （参考実装 `app_ref/services/worker/worker/registry.py` の `(Request, Result, process)` 三つ組規約に合わせる。）

- [ ] service の登録テーブルに `"stack-analysis": (StackAnalysisRequest, StackAnalysisResult, stack_analysis.process)` を追加する
      （016 で用意した service 側 registry / `/tasks/{pipeline}` ディスパッチへ接続）。

### service: タスクハンドラ（`/tasks/stack-analysis`）

- [ ] `POST /tasks/stack-analysis` が `StackAnalysisRequest` を受け、`stack_analysis.process` を実行する
      （ルーティング・OIDC 検証・GCS `$requestRef` 解決・mock-worker 配線は 016 のハンドラ規約に従う）。
- [ ] **冪等性（Cloud Tasks は at-least-once）:** 処理に入る前に `Job(job_id)` を読み、既に `COMPLETED` ならスキップする
      （`PROCESSING` へ遷移させてから処理を始め、完了時に upsert で `COMPLETED` にする）。同一タスクの再配送で結果が二重に
      ならないようにする。
- [ ] process 内で **Cloud SQL（pgvector pg17）への接続**を行い `save_stack` で `TechStack` を upsert する
      （service は自前の `backend/service/service/db.py` の `async_session_factory` を持つ。api と同じ DB を共有。
      `from shared.models import Job` で Job 行も同セッションで更新する）。
- [ ] **Vertex AI** を呼べるよう、service の runtime SA に `roles/aiplatform.user` を付与する前提で
      `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` + ADC を使う（API キー不使用。
      `gemini_stack_service._build_client` の方式を踏襲）。**Vertex AI のリージョンは Issue 016/017 で統一する
      キュー/インフラのロケーション（既定 `asia-northeast1`）に揃える** — 既存 `backend/app/core/config.py` の
      `GOOGLE_CLOUD_LOCATION` 既定は `us-central1` だが、解析パイプラインが叩く Vertex のリージョンを
      `asia-northeast1` に統一し、017 の `cloud-run.tf` が service に注入する `GOOGLE_CLOUD_LOCATION` と一致させる
      （`GOOGLE_CLOUD_LOCATION` の既定変更は 015/016 の config 統合タスクに反映）。
- [ ] 完了後、service が **自前の DB セッションで `Job` 行を直接更新** する：`status=COMPLETED`、
      `result_data`（JSONB）に `StackAnalysisResult` 由来の `agent_trace` + `languages` + `categories` を書く。
      `TechStack` の永続化（`save_stack`）と同じ DB へ書き込むので、結果は Cloud SQL に揃う（api への通知も Pub/Sub も無い）。
- [ ] 失敗時は `Job` 行を `status=FAILED` + `error_message`（`PipelineError` 要約）へ直接更新する
      （リトライは Cloud Tasks 側のバックオフに委ねる。再 enqueue 可能なよう `payload` は Job 行に残る）。

### api: `analyze-stack` を非同期化（`backend/api/app/api/v1/stack.py`）

- [ ] `POST .../analyze-stack` を以下に書き換える：
  1. `resolve_github_client` で GitHub installation token を mint（既存どおり）し、後述方式で `StackAnalysisRequest` を組む。
     `owner` / `repo` / `branch` / `requested_by`（= `current_user.id`、監査用）は **request payload に載せる**。
     service が完了時に該当 `Job` 行を直接更新できるよう、`job_id` も payload に含める。
  2. 016 の `job_orchestrator.enqueue_job(session, dispatcher, blob_client, job_type=JobType.STACK_ANALYSIS, payload=..., created_by=current_user.id)`
     を呼ぶ。`enqueue_job` が `Job`（`type=STACK_ANALYSIS`、`status=QUEUED`、`created_by=current_user.id`、`payload` に上記 request）を作成・flush し、
     上限超過時は GCS へスピルして `$requestRef` を載せ、`TaskDispatcher.dispatch("stack-analysis", request, dedup_key=str(job.id))`
     で Cloud Tasks に enqueue（HTTP ターゲット = service の `/tasks/stack-analysis`、OIDC トークン付き）する。
     - 発行者は 016 の `Job.created_by`（`UUID` \| null、FK → `users.id`）に `current_user.id` を設定して記録する。
       併せて service 側の監査ログ用に request payload にも `requested_by`（= `current_user.id`）を載せる
       （service は `created_by` 等の派生情報を payload からのみ参照するため。なお service は完了時に同じ `job_id` の `Job` 行を更新する）。
       `Job.project_id` は本 issue では設定しない
       （015 は Project モデルを未定義のため、016 側で `project_id` を **将来用の nullable・FK なし**として確定するまでは未使用）。
  3. `enqueue_job` が返した `Job` をもとに、`202 Accepted` で `{ "job_id": ..., "status": "QUEUED" }` を返す（`response_model` を新設）。
- [ ] `GET /api/v1/jobs/{job_id}`（016 で導入）が stack-analysis Job について
      `status` + `agent_trace` + `tech_stack`（完了時）を返せるよう、結果 payload 形を本パイプラインに合わせる
      （`agent_trace` は `Job.result_data` から、`tech_stack` は永続化済み `TechStack` から読む。
      いずれも service が Cloud SQL に直接書き込んだもの）。
- [ ] `GET .../stack` は **変更しない**（永続化済み `TechStack` を読むだけ。404 = 未解析の意味も維持）。
- [ ] 旧 `run_stack_analysis` の同期呼び出し・`app.agent.stack_agent` への import を api から削除する
      （api はエージェントを直接実行しない）。

### api: 結果は service が直接書く（コールバック無し）

- [ ] **結果受信エンドポイントは設けない。** service が処理完了時に Cloud SQL の `Job` 行を直接 `COMPLETED` + `result_data`
      （`agent_trace`）へ更新し、`TechStack` も永続化済みのため、api 側は受信処理を持たない
      （`POST /internal/jobs/results` や OIDC push 検証、Pub/Sub エンベロープ処理は本構成に存在しない）。api は `GET /jobs/{id}` で
      `Job.result_data` と `TechStack` を読むだけである。
- [ ] **stale-job タイムアウト掃除（016 の app_ref `result_poller._timeout_stale_jobs` 相当）:** Cloud Tasks にネイティブ DLQ は
      無いため、`PROCESSING` のまま閾値時間を超えて放置された Job を api 側で定期的に `FAILED` 化する掃除処理を持つ
      （`error_message` にタイムアウト理由を記録し、`payload` を残して再 enqueue 可能とする）。

### GitHub トークンの受け渡し（セキュリティ判断 — 必須）

参考実装 `app_ref/.../workflow_orchestrator.build_job_request`（`CODE_TO_SPEC`）は
`workflow_context.accessToken` を **request ペイロードに直接注入** しており、`CodeToSpecRepository.access_token` は
`SecretStr` で受けている。キューにアプリの秘密（GitHub installation token）を載せることになるため、本 issue では
以下から方式を選定し、推奨を明記する：

- [ ] **方式 A（参考実装互換・ペイロード注入）:** api が mint した **短命の** installation token を
      `StackAnalysisRequest.github.access_token`（`SecretStr`）に載せて enqueue する。
      - 長所：実装が単純・参考実装に一致。短所：トークンが Cloud Tasks のメッセージ本体（および GCS スピル時は
        `gs://` オブジェクト）に平文で乗る。
- [ ] **方式 B（推奨）:** **service が自前で mint する。** ペイロードには `installation_id`（または `owner`）のみを載せ、
      service が Secret Manager の `GITHUB_APP_PRIVATE_KEY`（既存 `backend/app/core/config.py`）から
      installation token を都度生成する（`github_app.GitHubAppService.get_installation_token` を service へ）。
      - 長所：キュー/GCS に秘密を残さない。GitHub App 秘密鍵は Secret Manager 一点管理で runtime SA のみが参照。
        短所：service にも GitHub App 認証経路が要る（ただし秘密鍵は Secret Manager 経由でゼロ平文）。

- [ ] **推奨は方式 B**。理由：CLAUDE.md「Secret Manager（プレーンテキスト環境変数は絶対不可）」と整合し、
      キューメッセージ・GCS スピルに秘密を残さない。方式 A を一時採用する場合でも、Cloud Tasks の TTL を短く保ち、
      GCS スピルオブジェクトには CMEK + 短命ライフサイクル削除を必須とする旨を本 issue 内に注記すること。

### frontend: 同期レスポンス → enqueue + ポーリングへ（`frontend/src/`）

- [ ] `frontend/src/lib/api/client.ts` の `analyzeStack(owner, repo)` を **`202 {job_id}` を返す** 形に変更し、
      `getJob(jobId)` / `getStack(owner, repo)` と組み合わせる（kebab-case ファイル名・既存 `apiFetch` 規約を維持）。
- [ ] `frontend/src/lib/api/schemas.ts` に `analyzeStackJobSchema`（`job_id` / `status`）と
      `jobStatusSchema`（`status` / `agent_trace` / `tech_stack?`）を追加する（Zod v4、snake_case フィールド保持）。
      `status` は 016 の `JobStatus` に合わせ **大文字の enum** とする
      （`z.enum(["QUEUED", "PROCESSING", "COMPLETED", "FAILED"])`）。`techStackSchema` は既存を流用。
- [ ] `frontend/src/lib/stores/stack-analysis-store.svelte.ts` を新設する（Svelte 5 クラスベース runes）：
  - `state: "idle" | "queued" | "processing" | "done" | "error"`（= ストア内部の UI 状態。`job.status` とは別物）、
    `jobId`、`trace: string[]`、`stack: TechStack | null`
  - `analyze(owner, repo)`（enqueue → `jobId` 保存 → ポーリング開始）/ `poll()`（`getJob` を間隔取得し、
    `job.status === "COMPLETED"` で `getStack` を読み確定、`job.status === "FAILED"` でエラー）/ `cancel()`（ポーリング停止）
- [ ] `frontend/src/lib/components/repo/tech-stack-panel.svelte` を改修し、「解析する」押下で enqueue → 進捗表示
      （`agent_trace` の最新行をステップ表示）→ 完了で従来のバッジ表示に合流させる。
      `analyzed_at` のフッター・再解析ボタンは維持。
- [ ] `frontend/messages/ja.json` / `en.json`（Paraglide 2.0、ja 主・en 従）に進捗文言を追加
      （`stack_analyzing` / `stack_step_listing` / `stack_step_reading` / `stack_step_classifying` / `stack_step_saving` /
      `stack_failed` 等）。`agent_trace` の `[call] / [done] / [summary]` を人間可読ステップへマップするヘルパを置く。

### テスト

- [ ] api（`backend/api/tests/`）：`POST analyze-stack` が `202` + `job_id` を返し、`Job` が `QUEUED` で作成され、
      `MockTaskDispatcher.dispatch` がモックで 1 回呼ばれること（`job_orchestrator.enqueue_job` 経由）。
      エージェントを **直接実行しない**こと（旧 import なし）。
- [ ] api：`GET /jobs/{id}` が stack-analysis Job の `status` / `agent_trace` / 完了時 `tech_stack` を返すこと
      （`Job.result_data` / `TechStack` を読む）。stale-job 掃除が `PROCESSING` 放置 Job を `FAILED` 化すること。
- [ ] service（`backend/service/tests/`）：`stack_analysis.process` のパイプラインテスト
      （`GitHubGitClient` と Gemini/Vertex を **モック**）。`save_stack` で `TechStack` が upsert され、
      service が `Job` 行を `COMPLETED` + `result_data`（`agent_trace`）へ直接更新すること。再配送（at-least-once）で
      既に `COMPLETED` の Job が二重更新されない冪等性のテスト。GitHub トークンを **方式 B** で service が mint する経路のテスト。
- [ ] e2e（mock-worker 経由）：`analyze-stack` enqueue → mock-worker が `/tasks/stack-analysis` を叩く →
      service が Cloud SQL に `TechStack` + `Job(COMPLETED)` を書く → `GET /jobs/{id}` が `COMPLETED`、
      `GET .../stack` で `TechStack` が取得できる、の往復が通ること（016 の mock-worker / エミュレータ配線を利用）。
- [ ] frontend：`stack-analysis-store` のユニットテスト（`analyze` / `poll` / 状態遷移、API モック）と
      `tech-stack-panel.svelte.spec.ts`（browser-mode：enqueue → 進捗 → 完了表示）。

## 完了条件

- フロントの「解析する」押下で api が **`202` + `job_id`** を返し、**api リクエストはエージェント完了を待たずに
  即座に返る**（エージェント実行で api ワーカーが塞がらない）。
- service が **api リクエスト外**でエージェント（`list_key_files`→`read_file`→`classify_stack`→`save_stack`）を実行し、
  `TechStack` を Cloud SQL に永続化する。
- service が処理完了後、自前の DB セッションで `Job` 行を `COMPLETED`/`FAILED` + `result_data`（`agent_trace`）に
  **Cloud SQL 直接書き込み**し、api への結果コールバックや Pub/Sub publish が一切無いこと。
- フロントが `GET /jobs/{id}` をポーリングして **進捗（`agent_trace` ベース）→ 結果表示**へ遷移し、
  完了後は従来どおりのバッジ表示になる。
- `GET .../stack` が（インターフェース不変のまま）永続化済み `TechStack` を返す。
- GitHub トークンの受け渡しが本 issue で決めた方式（推奨：方式 B）で実装され、**キュー/GCS に平文の秘密が残らない**
  （方式 A 暫定時は TTL/CMEK/短命削除の注記どおり）。
- バックエンド：`cd backend && uv run pytest` / `uv run ruff check && uv run ruff format --check` / `uv run ty check` が通る
  （api・service の両ワークスペースメンバー）。
- フロント：`cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Changed`（analyze-stack を非同期化）/`Added`（stack-analysis パイプライン）の追記。

## 技術詳細

### Before / After シーケンス

**Before（現状・同期、api 内で完結）:**

```
Browser ── POST /analyze-stack ──▶ api (Cloud Run)
                                     │ resolve_github_client → installation token
                                     │ run_stack_analysis (ADK Runner)
                                     │   list_key_files → read_file×N
                                     │   → classify_stack(Vertex AI) → save_stack(DB)
                                     │ （この間 api ワーカーをブロック）
Browser ◀────── 200 TechStackOut ───┘
```

**After（非同期・service 実行、Cloud Tasks=request / 結果は service が Cloud SQL 直書き）:**

```
Browser ─ POST /analyze-stack ─▶ api ─ enqueue_job(STACK_ANALYSIS) → Job(QUEUED)
                                  └─ dispatch("stack-analysis", payload) ─▶ Cloud Tasks
Browser ◀── 202 {job_id} ─────────┘
                                            Cloud Tasks ─ OIDC HTTP ─▶ service (ingress=internal)
                                                            POST /tasks/stack-analysis
                                                              （冪等チェック: Job が COMPLETED ならスキップ）
                                                              Job → PROCESSING
                                                              stack_analysis.process()
                                                                ADK Runner（list→read→classify→save）
                                                                save TechStack → Cloud SQL
                                                              update Job → COMPLETED (+ result_data: agent_trace)
                                                                ─▶ Cloud SQL（service が直接書き込み）
Browser ─ GET /jobs/{id} (poll) ─▶ api ─ {status, agent_trace, tech_stack?}  ← Job.result_data / TechStack を読む
Browser ─ GET .../stack ────────▶ api ─ 永続化済み TechStack（不変）
```

### stack-analysis の Job ペイロード（推奨：方式 B）

```jsonc
// Cloud Tasks の HTTP ボディ（service の /tasks/stack-analysis 宛）
{
  "job_id": "0190a1f2-...",          // api が作成した Job の id
  "owner": "acme",
  "repo": "rosetta",
  "branch": "main",
  "requested_by": "0190a0aa-...",    // current_user.id（監査用）
  "github": {
    "installation_id": 12345678       // 方式 B: 秘密は載せない。service が Secret Manager から mint
    // 方式 A（参考実装互換・非推奨）の場合のみ: "access_token": "<short-lived installation token>"
  }
}
```

request ペイロードが Cloud Tasks のメッセージ上限を超える場合は、016 のスピルオーバー規約に従い GCS へ退避し、
メッセージには `{"$requestRef": "gs://<bucket>/requests/stack-analysis/<job_id>.json"}` を載せる
（参考実装の `blob://` 相当を `gs://` で実装）。**結果は Cloud SQL の `Job.result_data` に直接書くため、結果側の
GCS スピル（`$resultRef`）は不要**。スピルバケットは 017 の Terraform 命名規約に従い
`<project_name>-<environment>-job-payloads`（016 の `JOB_PAYLOAD_BUCKET` に注入）。
オブジェクトパスのレイアウト（`requests/{pipeline}/{job_id}.json`）は 016 の `gs://` 参照フォーマットに従う。

### GitHub トークンをペイロードに載せる場合のセキュリティ注記

| 観点 | 方式 A（ペイロード注入） | 方式 B（service 自前 mint・推奨） |
|---|---|---|
| キュー/GCS 上の秘密 | installation token が平文で乗る | 乗らない（`installation_id` のみ） |
| 秘密の保管 | api と Cloud Tasks/GCS に散る | Secret Manager 一点（`GITHUB_APP_PRIVATE_KEY`） |
| 失効までの露出 | token TTL（〜1h）の間 | mint は service 内のみ・即時利用 |
| 実装難易度 | 低（参考実装と同形） | 中（service に GitHub App 認証経路） |
| 必要な追加対策 | Cloud Tasks 短 TTL + GCS の CMEK / 短命ライフサイクル削除 + ログにトークンを出さない | service runtime SA に Secret Manager 参照権限 |

> 推奨：**方式 B**。CLAUDE.md「Secret Manager / プレーンテキスト環境変数は絶対不可」と整合し、参考実装の
> `access_token` ペイロード注入が持つ「キューに秘密が残る」リスクを回避する。方式 A は暫定実装に限り、
> 上表の追加対策を必須とする。

### フロントのポーリング（抜粋）

```typescript
// frontend/src/lib/stores/stack-analysis-store.svelte.ts
import { analyzeStack, getJob, getStack } from "$lib/api/client";
import type { TechStack } from "$lib/api/schemas";

class StackAnalysisStore {
  state = $state<"idle" | "queued" | "processing" | "done" | "error">("idle");
  trace = $state<string[]>([]);
  stack = $state<TechStack | null>(null);
  jobId: string | null = null;
  #timer: ReturnType<typeof setTimeout> | null = null;

  async analyze(owner: string, repo: string) {
    this.state = "queued";
    const { job_id } = await analyzeStack(owner, repo); // 202 {job_id}
    this.jobId = job_id;
    this.#poll(owner, repo);
  }

  async #poll(owner: string, repo: string) {
    if (!this.jobId) return;
    const job = await getJob(this.jobId);
    this.trace = job.agent_trace ?? [];
    if (job.status === "COMPLETED") {
      this.stack = await getStack(owner, repo); // 永続化済みを読む（GET .../stack は不変）
      this.state = "done";
      return;
    }
    if (job.status === "FAILED") {
      this.state = "error";
      return;
    }
    this.state = "processing";
    this.#timer = setTimeout(() => this.#poll(owner, repo), 1500);
  }

  cancel() {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = null;
  }
}

export const stackAnalysis = new StackAnalysisStore();
```

### 移設ファイル対応表

| 移設前（モノリス） | 移設後（uv workspace） | 備考 |
|---|---|---|
| `backend/app/agent/stack_agent.py` | `backend/service/service/pipelines/stack_analysis.py` | `process(request)` に統一。ADK Runner を service で実行 |
| `backend/app/services/gemini_stack_service.py` | `backend/service/service/services/gemini_stack_service.py` | Vertex AI 呼び出し。SA に `roles/aiplatform.user` |
| `backend/app/services/github_git_client.py` | `backend/service/service/services/github_git_client.py` | `httpx` 依存のため shared に置かず service へ。api は既存実装を保持 |
| `backend/app/services/github_app.py` | `backend/service/service/services/github_app.py`（api 側にも残す） | 方式 B で service が installation token を mint。`PyJWT`/`cryptography` 依存のため shared に置かない |
| `backend/app/api/v1/stack.py`（`TechItemOut` / `TechCategoriesOut`） | `backend/shared/shared/schemas/stack_analysis.py`（`TechItem` / `TechCategories`） | request/result スキーマへ昇格 |
| `backend/app/models/tech_stack.py`（`TechStack`） | `backend/shared/shared/models/tech_stack.py`（`TechStack`） | service が直接書くため shared へ移設。`from shared.models import TechStack`。マイグレーションは api 所有 |
| `backend/app/api/v1/stack.py::analyze_stack`（同期実行） | `backend/api/app/api/v1/stack.py::analyze_stack`（enqueue + 202） | エージェント実行は service へ。直接 import を削除 |
| `backend/app/api/v1/stack.py::get_stack` | `backend/api/app/api/v1/stack.py::get_stack` | **変更なし**（永続化済み TechStack を読む） |

### 既存の保持ポイント

- `tech_stacks` テーブル（`backend/app/models/tech_stack.py`）と `uq_tech_stacks_owner_repo` 制約・upsert ロジックは
  そのまま service の `save_stack` で利用（スキーマ変更なし）。**service が `TechStack` を直接書き込むため、`Job` と同様に
  `TechStack` モデルも `shared`（`backend/shared/shared/models/`）へ移し、api・service の双方が `from shared.models import TechStack`
  で参照できるようにする**（Alembic マイグレーションと DB エンジン/セッションは api が所有。service は `backend/service/service/db.py`
  の薄いセッションで shared モデルに DML するのみ）。
- `_KEY_FILENAMES` / `_KEY_EXTENSIONS` / `_MAX_TOOL_FILES=10` / `_MAX_FILE_CHARS=5000` のヒューリスティクスは
  パイプラインへそのまま移送する（解析品質を変えない）。
- フロントの `confidence` バッジ・カテゴリラベル（`tech-stack-panel.svelte`）は再利用。完了表示は従来どおり。

## 参考

- 関連 Issue（相互参照）
  - `docs/issue/015-backend-api-service-split-monorepo.md` — api/service 分割・uv workspace 基盤（前提）
  - `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks + Job（shared）+ GCS スピル + mock-worker（前提）
  - `docs/issue/017-terraform-gcp-infrastructure.md` — GCP 版 Terraform（service Cloud Run / Cloud Tasks キュー / GCS / SA 権限のプロビジョン）
  - `docs/issue/004-adk-stack-analysis-agent.md` — 本 issue が非同期化する ADK エージェントの初版実装
- 現行実装（移設・改修対象）
  - `backend/app/api/v1/stack.py` — `analyze_stack`（同期）/ `get_stack`（不変）
  - `backend/app/agent/stack_agent.py` — ADK `Runner`・`build_tools`・`run_stack_analysis`
  - `backend/app/services/gemini_stack_service.py` — Gemini/Vertex AI 分類
  - `backend/app/api/v1/github.py` — `resolve_github_client`（installation token mint）
  - `backend/app/models/tech_stack.py` — `tech_stacks`（upsert 先・スキーマ不変）
  - `backend/app/core/config.py` — `GOOGLE_CLOUD_PROJECT` / `GEMINI_MODEL` / `GITHUB_APP_PRIVATE_KEY`（方式 B の鍵元）
  - `frontend/src/lib/components/repo/tech-stack-panel.svelte` — 同期 UI（改修対象）
  - `frontend/src/lib/api/client.ts` — `analyzeStack` / `getStack`（改修対象）
  - `frontend/src/lib/api/schemas.ts` — `techStackSchema` 等（流用 + Job スキーマ追加）
- 参考実装（`app_ref/services/`）
  - `app_ref/services/api/app/api/analysis.py` — enqueue + `202 {jobId}` + `GET /analyze/{job_id}` ポーリング（mock 進捗込み）
  - `app_ref/services/api/app/services/workflow_orchestrator.py` — `build_job_request`（`accessToken` ペイロード注入）/ `enqueue_job`（blob スピル）
  - `app_ref/services/worker/worker/registry.py` — `(Request, Result, process)` 三つ組のパイプライン登録規約
  - `app_ref/services/shared/shared/schemas/code_to_spec.py` — `access_token: SecretStr`（方式 A の参照形）
- 規約
  - `CLAUDE.md` — Python=snake_case / フロント=kebab-case、Svelte 5 runes、Paraglide 2.0、Secret Manager 必須、
    Vertex AI + ADC（API キー不使用）、PATCH 規約、`uv run pytest` / `ruff` / `ty` / `bun run check` ゲート
