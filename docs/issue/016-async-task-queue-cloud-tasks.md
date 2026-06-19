# Cloud Tasks による api→service 非同期タスク基盤を実装する

## 概要

issue-015 で分割した `api` / `service` の 2 コンテナ間に、**キューによる
api→service タスク依頼**と**結果の永続化**の汎用プラミングを実装する。これはユーザーの中核要望
（「api からの重い処理依頼をキューで service に投げ、非同期で処理する」）の本体である。

設計判断は以下のとおり（request ディスパッチのみマネージドキューを使い、result は DB 直書き）：

- **request（api→service タスク依頼）= Cloud Tasks** — HTTP ターゲット `service` の
  `POST /tasks/{pipeline}` を OIDC トークン付きで叩く。点対点ディスパッチ・リトライ・
  バックオフ・レート制御・重複排除に最適で、参考実装の **request キュー** に最も近い。
- **result（service→DB 結果書き込み）= service が Cloud SQL に直接書き込み** — `service` の
  `/tasks/{pipeline}` ハンドラが処理完了後、自前の DB セッションで `Job` 行を
  `COMPLETED` / `FAILED` + `result_data` に更新し、ドメイン結果も書き込む。**api への
  コールバックも push 受信エンドポイントも不要**。フロントは `GET /api/v1/jobs/{id}` を
  ポーリングして完了を検知する。
- **大きいペイロードのスピルオーバー = Cloud Storage (GCS)** — キューのメッセージサイズ
  上限を超える request は `gs://` に退避し、メッセージには `$requestRef`
  （参考実装 `app_ref` の `blob://` 相当）を載せる。

本 issue では汎用基盤と **Job ライフサイクル** を実装し、末尾に自明な `ping` / `echo`
パイプラインを通して **end-to-end を実証**する。実際の重い処理（ADK スタック解析）の
移行は issue-018 で行う。ローカルは GCP 不要の **in-memory mock dispatcher +
mock-worker** で回す。

## 背景・目的

### 現状（モノリス・キューなし・Job モデルなし）

- 現状の `backend/` は単一の FastAPI モノリスで、worker もキューも **Job モデルも無い**
  （`backend/app/main.py` の lifespan は DB engine の dispose のみ、`backend/app/core/config.py`
  にキュー関連設定は無い）。
- 解析系のエンドポイント（issue-004 の ADK スタック解析）は **リクエストスレッド内で
  同期実行**されており、重い処理が api のレイテンシ・スケールに直撃する。
- 参考実装 `app_ref/services/` は Azure Queue Storage ベースで **request / result の双方向
  キュー**＋ **blob スピルオーバー**を持つが、本プロジェクトの制約は **GCP**（CLAUDE.md の
  必須サービスに準拠）。よって request の Azure Queue → Cloud Tasks、Blob → GCS に写像し、
  result の Azure Queue（長ポーリング）は **service が Cloud SQL に直接書き込む**方式に置換する。

### 目的

1. `api` が重い処理を **fire-and-forget で `service` に依頼**できる汎用 `TaskDispatcher` を整える。
2. **Job** を第一級エンティティとして DB に永続化し、`QUEUED → PROCESSING → COMPLETED / FAILED`
   のライフサイクルを管理する。`api` が `enqueue_job` で `QUEUED` を作成し、`service` が処理後に
   `COMPLETED` / `FAILED` へ直接書き込む。フロントは `GET /api/v1/jobs/{id}` をポーリングする。
3. **結果を service が Cloud SQL に直接書き込む**（参考実装の長ポーリング `result_poller` が担っていた
   「DB への結果永続化」を service 側に移し、api 側の受信エンドポイント・ポーリングループを廃止）。
   これにより `service` も `api` も常時ポーリングするバックグラウンドループを持たず、Cloud Run の
   リクエスト駆動・ゼロスケールに適合する。
4. **大ペイロードを GCS にスピル**して、キューのメッセージサイズ上限に縛られない。
5. **ローカルは GCP 不要**（in-memory mock）で end-to-end が回り、テストで担保される。

### 前提 Issue（depends_on）

- **issue-015**（`docs/issue/015-backend-api-service-split-monorepo.md`） — `backend/` を
  uv workspace ルート化し、メンバーを `shared` / `api` / `service` に分割する基盤。本 issue の
  `shared`（`Job` モデル・enum・スキーマ）/ `api`（dispatcher・enqueue・`GET /jobs/{id}`）/ `service`
  （`/tasks/{pipeline}` ハンドラ・DB 直書き）の配置は **015 のツリーを前提**とする。
  015 が未マージの場合、本 issue は **新規ファイルの追加が中心**なので
  `backend/app/`（= 将来の `api/app/`）配下に先行配置し、015 マージ時に `api/` 下へ移送してよい。

### 独自性（参考実装の丸写しにしない）

参考実装は **request / result とも Azure Queue Storage の長ポーリング**だが、本設計は
GCP のマネージド特性に合わせて **request=Cloud Tasks（push）/ result=service が Cloud SQL に
直接書き込み**にする。これにより `service` も `api` も **常時ポーリングするバックグラウンド
ループを持たず**、HTTP リクエスト到来時のみ起動する（Cloud Run のゼロスケールと整合）。
参考実装の `result_poller.poll_all_result_queues()`（無限ループで result キューを読み DB へ
永続化）は、**`service` の `/tasks/{pipeline}` ハンドラが処理完了時に Cloud SQL の `Job` 行を
直接更新する**ことへ置き換わる点が最大の差分である。result 用のキュー・トピック・api 側の
受信エンドポイントは一切持たない。

## タスク

### shared（`shared/shared/` — `Job` モデル・Protocol・enum・基底スキーマ）

- [ ] `shared/shared/models/job.py` に **`Job`（SQLModel）** を新設する（api / service の
      双方が `from shared.models import Job` で利用する。テーブル定義の単一の真実点）。
      **shared の依存は `pydantic>=2` + `sqlmodel`** に限定する（統合クライアント＝
      github / gemini / httpx / PyJWT は引き続き shared に置かない）。
      カラム定義は後述の api セクション (1) を参照。**Alembic マイグレーションと
      「DB エンジン / セッション生成」は api が所有**し、service は自前の薄い
      `service/service/db.py` で同じ `Job` モデルに対し DML するのみ（マイグレーションは実行しない）。

- [ ] `shared/shared/enums.py` に `JobType` / `JobStatus` を追加する
      （`app_ref/services/shared/shared/enums.py` の `StrEnum` パターンを踏襲）

  ```python
  from enum import StrEnum

  class JobType(StrEnum):
      ECHO = "echo"            # end-to-end 実証用の自明パイプライン
      PING = "ping"            # health 確認用の最小パイプライン
      STACK_ANALYSIS = "stack_analysis"  # issue-018 で実装（プレースホルダ）

  class JobStatus(StrEnum):
      QUEUED = "QUEUED"
      PROCESSING = "PROCESSING"
      COMPLETED = "COMPLETED"
      FAILED = "FAILED"
      CANCELLED = "CANCELLED"

  class ResultStatus(StrEnum):
      COMPLETED = "COMPLETED"
      FAILED = "FAILED"
      PARTIAL = "PARTIAL"
  ```

  > **enum 値は大文字に統一**する（メンバ名・`value` ともに大文字の `StrEnum`。
  > `app_ref/services/shared/shared/enums.py` の `JobStatus` / `ResultStatus` 規約を踏襲）。
  > issue-018 の `Job.status` 判定・フロントの Zod スキーマ・ポーリング判定
  > （`job.status === "COMPLETED"`）もこの大文字値を前提とするため、全 Issue でこの casing に揃える。
  > 永続値・API 応答・キューメッセージはすべて大文字（`"QUEUED"` / `"PROCESSING"` / `"COMPLETED"` / `"FAILED"`）。

- [ ] `shared/shared/queue.py` に `TaskDispatcher` / `BlobClient` の
      Protocol を定義する（`app_ref/.../interfaces.py` の `QueueClient` / `BlobClient`
      Protocol を GCP 風に移植。Azure の `send_message / receive_messages / delete_message`
      は **Cloud Tasks の push 前提のため不要**になり、API が変わる点に注意。
      result はキュー / publisher を経由せず service が DB 直書きするため `ResultPublisher`
      Protocol は設けない）

  ```python
  from typing import Any, Protocol

  class TaskDispatcher(Protocol):
      async def dispatch(self, pipeline: str, payload: dict[str, Any], *, dedup_key: str | None = None) -> None:
          """Cloud Tasks の HTTP タスクを作成し、service の /tasks/{pipeline} に向ける。"""
          ...

  class BlobClient(Protocol):
      async def upload(self, bucket: str, object_path: str, data: bytes,
                       content_type: str = "application/json") -> str:
          """データを GCS にアップロードし gs://bucket/object_path を返す。"""
          ...
      async def download_from_url(self, gcs_url: str) -> bytes:
          """gs:// URL を解決してダウンロード。"""
          ...
      async def exists(self, bucket: str, object_path: str) -> bool: ...
      async def delete(self, bucket: str, object_path: str) -> None: ...
  ```

- [ ] `shared/shared/gcs.py` に `parse_gcs_url(url) -> tuple[bucket, object_path]` を実装する
      （`app_ref/services/shared/shared/blob.py` の `parse_blob_url`（`blob://` → `(container, path)`）
      を `gs://` 用に写経）
- [ ] `shared/shared/schemas/base.py` に `SharedBaseModel`（`alias_generator=to_camel`,
      `populate_by_name=True`）と `PipelineError` / `PipelineTiming` を追加する
      （`app_ref/.../schemas/base.py` をそのまま踏襲。request はキューを跨ぐので camelCase 共通語彙にする）
- [ ] `shared/shared/schemas/job.py` に **Job request / result の基底スキーマ** と
      `echo` / `ping` の具象スキーマを定義する

  ```python
  class JobRequestBase(SharedBaseModel):
      job_id: str
      job_type: JobType
      schema_version: str = "1.0"

  class JobResultBase(SharedBaseModel):
      job_id: str
      job_type: JobType
      status: ResultStatus
      error: PipelineError | None = None
      timing: PipelineTiming | None = None

  class EchoRequest(JobRequestBase):
      message: str

  class EchoResult(JobResultBase):
      echoed: str | None = None
  ```

### api（`api/app/` — dispatcher・enqueue・`GET /jobs/{id}`・Alembic 所有）

- [ ] **(1) `Job` SQLModel（`shared` 由来）+ Alembic マイグレーション（api 所有）**（現状 Job モデルは無い）
  - `Job` モデルそのものは **`shared/shared/models/job.py`** に置き（前述 shared セクション）、
    api は `from shared.models import Job` で参照する。**Alembic マイグレーションと DB エンジン /
    セッション生成は api が所有**する（`api/app/core/db.py`）。

    | カラム | 型 | 備考 |
    |---|---|---|
    | `id` | `UUID` (PK) | `default uuid4` |
    | `type` | `JobType` (enum) | `ECHO` / `PING` / `STACK_ANALYSIS` |
    | `status` | `JobStatus` (enum) | 既定 `QUEUED` |
    | `payload` | `JSONB` | enqueue 時の request（camelCase）。大は `{"$requestRef": "gs://..."}` |
    | `result_data` | `JSONB` \| null | 完了時に **service が直接書き込む**結果（camelCase）。issue-018 はここに `agent_trace` を格納する |
    | `error_message` | `text` \| null | FAILED 時のエラー要約 |
    | `created_by` | `UUID` \| null (FK → `users.id`) | Job を作成したユーザ。api の `enqueue_*` が `current_user.id` を設定（issue-018 の `created_by=current_user.id` と一致） |
    | `project_id` | `UUID` \| null | **将来の Project（未実装）に紐付ける任意カラム。本 issue では nullable・FK 制約なし**（issue-015 は Project モデルを定義しないため依存しない） |
    | `created_at` | `timestamptz` | |
    | `started_at` | `timestamptz` \| null | PROCESSING 遷移時 |
    | `completed_at` | `timestamptz` \| null | COMPLETED / FAILED 時 |

  - [ ] `cd backend && uv run alembic revision --autogenerate -m "add job table"` で
        マイグレーションを生成し（**api がマイグレーションを所有**。`Job` を `shared` から import して
        autogenerate の target metadata に含める）、`jobstatus` / `jobtype` の enum 型を確認する
  - [ ] `JobStatus` / `JobType` は `shared` 由来の `StrEnum` を `sa_column=Column(SAEnum(...))` で永続化する

- [ ] **(2) Dispatcher 実装と settings 切替**（`app_ref` の `get_queue_client` / `is_mock_queue` 踏襲）
  - `api/app/services/cloud_tasks_dispatcher.py` — `CloudTasksDispatcher`（`google-cloud-tasks`）
    - `dispatch(pipeline, payload, dedup_key)` で `CreateTaskRequest` を作る
    - `http_request.url = f"{settings.SERVICE_TASKS_URL}/tasks/{pipeline}"`、`http_method=POST`
    - `oidc_token`（`service_account_email = settings.TASKS_INVOKER_SA`,
      `audience = settings.SERVICE_TASKS_URL`）を付与（service の ingress=internal + 認可に必須）
    - `dedup_key` が与えられたら `task.name`（= `tasks/{dedup}`）で **重複排除**
    - リトライ/バックオフは **Cloud Tasks キュー側の設定**（issue-017 でプロビジョン）に委ねる
  - `api/app/services/mock_task_dispatcher.py` — `MockTaskDispatcher`（in-memory）
    - `dispatch` で `(pipeline, payload)` を内部リストに積み、**mock-worker** が拾って処理する
  - `api/app/services/dependencies.py` に `get_task_dispatcher()` を追加（`app_ref` の `get_queue_client` 形）

    ```python
    _mock_dispatcher: MockTaskDispatcher | None = None

    def get_task_dispatcher() -> TaskDispatcher:
        global _mock_dispatcher
        if settings.use_mock_queue():
            if _mock_dispatcher is None:
                _mock_dispatcher = MockTaskDispatcher()
            return _mock_dispatcher
        from app.services.cloud_tasks_dispatcher import CloudTasksDispatcher
        return CloudTasksDispatcher(...)

    def reset_task_dispatcher() -> None:  # tests 用
        global _mock_dispatcher
        _mock_dispatcher = None
    ```

  - `get_blob_client()` を追加：`settings.use_mock_blob()` で `MockBlobClient` / 既定 `GcsBlobClient`

- [ ] **(3) `enqueue_job()`**（`api/app/services/job_orchestrator.py`。`app_ref` の
      `workflow_orchestrator.enqueue_job` を踏襲：ペイロード構築 → GCS スピル判定 → タスク作成 →
      Job=QUEUED 永続化）
  - 関数名は **`enqueue_job`** に統一する（issue-018 の `analyze-stack` ルートとテストが
    `enqueue_job` を参照するため。`TaskDispatcher.dispatch` は dispatcher 側の低レベル API、
    `enqueue_job` は Job 永続化 + スピル + dispatch を束ねる orchestrator 関数という役割分担）

  ```python
  _MAX_TASK_REQUEST_BYTES = 90_000   # Cloud Tasks の body 上限 ~100KB を下回る安全値
  _REQUEST_BLOB_PREFIX = "requests"

  async def enqueue_job(*, session, dispatcher, blob_client, job_type, payload,
                         created_by=None, project_id=None) -> Job:
      job = Job(type=job_type, status=JobStatus.QUEUED, payload=payload,
                created_by=created_by, project_id=project_id)
      session.add(job)
      await session.flush()  # job.id 確定（参考実装と同様、enqueue 前にコミット可視化）

      request = {"jobId": str(job.id), "jobType": job_type, **payload}
      message = json.dumps(request)
      if len(message.encode()) > _MAX_TASK_REQUEST_BYTES:
          object_path = f"{_REQUEST_BLOB_PREFIX}/{job_type}/{job.id}.json"
          gcs_url = await blob_client.upload(settings.JOB_PAYLOAD_BUCKET, object_path, message.encode())
          request = {"jobId": str(job.id), "jobType": job_type, "$requestRef": gcs_url}

      await session.commit()
      await dispatcher.dispatch(str(job_type), request, dedup_key=str(job.id))
      return job
  ```

- [ ] **(4) stale-job タイムアウト掃除**（`app_ref` の `result_poller._timeout_stale_jobs` 相当。
      result はもう api に届かないため、結果待ちエンドポイントは持たない）
  - `api/app/services/job_orchestrator.py` に `timeout_stale_jobs(session, *, max_age)` を置く：
    `PROCESSING` のまま `started_at` が一定時間（既定はキューの最大試行 ×ack 期限より十分長く）
    放置された Job を `FAILED`（`error_message="timed out"`）に遷移させる
  - 起動方法は本 issue では **api のスタートアップ時に一度掃く / 管理エンドポイントから手動起動**で足り、
    定期実行のスケジューラ化は後続に委ねる（Cloud Tasks は at-least-once で恒久失敗を `Job(FAILED)` に
    残すため、放置 Job の主因は service クラッシュ等に限られる）

  > **api には push 受信エンドポイントを置かない。** 結果は service が Cloud SQL に直接書き込む方式
  > （後述 service セクション）に統一したため、`POST /internal/jobs/results` / Pub/Sub エンベロープ
  > デコード / push の OIDC 検証は実装しない。

- [ ] **(5) `GET /api/v1/jobs/{id}`**（フロントのポーリング用。`api/app/api/v1/jobs.py`）
  - Job を `id` で引き、`id` / `type` / `status` / `result_data` / `error_message` / 各 timestamp を返す
  - 404（存在しない / 他 org の Job）と、`status` に応じた `result_data` の有無をスキーマで表現
  - service が同じ DB に書き込んだ最新状態をそのまま読むだけで、`status === "COMPLETED"` で
    フロントのポーリングが終了する

### service（`service/service/` — `/tasks/{pipeline}` ハンドラ・DB 直書き・pipelines）

- [ ] `service/service/db.py` — service 用の薄い engine / session を作る（`DATABASE_URL` +
      Cloud SQL 接続）。**shared の `Job` モデルに対し DML するのみで、Alembic マイグレーションは
      実行しない**（マイグレーション所有は api）。`async_sessionmaker` を 1 つ用意する程度。
- [ ] `service/service/main.py` に FastAPI を立てる：`GET /health` と `POST /tasks/{pipeline}`
      （`app_ref` の `worker/main.py` の `_poll_queue` セマンティクスを **HTTP 駆動に翻案**）
- [ ] `POST /tasks/{pipeline}` ハンドラ
  - **Cloud Tasks の OIDC 検証**（`Authorization: Bearer`、`aud == SERVICE_TASKS_URL`、
    `email == TASKS_INVOKER_SA`）。失敗は 401。ローカル mock では検証スキップ（`USE_MOCK_QUEUE`）
  - body を解析し `$requestRef` を解決（`app_ref` の `_resolve_request_ref` を GCS 化）
  - **冪等性チェック（at-least-once 対策）**：`jobId` で `Job` を引き、既に `COMPLETED` なら
    何もせず **2xx を返して ack**（重複配信をスキップ）。それ以外は `PROCESSING` + `started_at` に更新
  - `pipeline` から `(request_model, result_model, process_fn)` を引く（registry）
  - `process_fn(request, ctx)` を実行 → 結果 `JobResultBase` を組み立てる
  - **結果を service の DB セッションで直接書き込む**：`Job` 行を `COMPLETED` + `result_data`
    （+ `completed_at`）に更新し、ドメイン結果（例 issue-018 の `TechStack`）も同一トランザクションで書く。
    api へのコールバックも publish も行わない
  - **ack / リトライの方針**：
    - 成功 → `Job=COMPLETED` を書いてから **2xx で ack**
    - `process_fn` の **恒久失敗**（入力不正・ドメインエラー）→ `Job=FAILED` + `error_message` を
      書いてから **2xx で ack**（Cloud Tasks に再試行させない）
    - **一時失敗**（DB / GCS など基盤の一過性エラー）→ Job を確定させず **5xx を返して Cloud Tasks に
      再試行**させる（キューの `maxAttempts` 超過まで再配信。冪等チェックで二重処理を防ぐ）
- [ ] `service/service/registry.py` — `PIPELINES: dict[str, tuple[type, type, callable]]`
      （`app_ref` の `worker/registry.py` 踏襲）。本 issue では `echo` / `ping` の 2 つ
- [ ] `service/service/pipelines/echo.py` / `ping.py` — 自明な `process(request, ctx)`
  - `echo`：`message` をそのまま `echoed` に返す（任意で `asyncio.sleep` で「重さ」を模擬）
  - `ping`：`{"pong": true}` 相当の最小結果を返す
- [ ] `service/service/context.py` — `PipelineContext`（`blob` / DB セッション / 設定を束ねる
      dataclass。`app_ref` の `worker/context.py` を簡素化。result publisher は持たない）

### blob（GCS スピルオーバー）

- [ ] `shared/shared/` か各メンバーに `GcsBlobClient`（`google-cloud-storage`）と
      `MockBlobClient`（in-memory dict）を実装する
  - `upload` は `gs://{bucket}/{object_path}` を返す（`app_ref` の `blob://` 戻り値の GCS 版）
  - `download_from_url` は `parse_gcs_url` で `(bucket, object_path)` に分解して取得

### ローカル開発（GCP なしで回す）

- [ ] `api/app/core/config.py`（= 現 `backend/app/core/config.py`）に設定を追加する
      （`app_ref` の `use_mocks` / `use_mock_worker` 踏襲。`SecretStr` は使わず公開値のみ）
  - **設定キー名は既存 `config.py` と issue-017 の Cloud Run env 注入名に一字一句揃える。**
    既存の `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`（Vertex AI / ADC 用、現状すでに存在）を
    **再利用**し、新規にプロジェクト ID 用キーを増やさない。キュー / バケット / service URL は
    issue-017 の `cloud-run.tf` が注入する名前（`TASKS_QUEUE` / `JOB_PAYLOAD_BUCKET` /
    `SERVICE_TASKS_URL`）と一致させる（不一致だと Settings 解決時にクラッシュする）。

  ```python
  USE_MOCK_QUEUE: bool = Field(default=True)   # in-memory dispatcher
  USE_MOCK_WORKER: bool = Field(default=True)  # mock-worker を起動して service を肩代わり
  USE_MOCK_BLOB: bool = Field(default=True)    # in-memory blob

  SERVICE_TASKS_URL: str = Field(default="http://localhost:8001")  # Cloud Tasks の HTTP ターゲット（service）
  TASKS_INVOKER_SA: str = Field(default="")     # Cloud Tasks → service の OIDC SA
  # GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION は既存（Vertex AI / ADC 用）を再利用する。
  # Cloud Tasks のロケーションは GOOGLE_CLOUD_LOCATION を共用し、専用キーは設けない。
  TASKS_QUEUE: str = Field(default="job-requests")        # request キュー名（issue-017 で作成）
  JOB_PAYLOAD_BUCKET: str = Field(default="")             # スピルオーバー用 GCS バケット（issue-017 outputs から注入）

  def use_mock_queue(self) -> bool: return self.USE_MOCK_QUEUE
  def use_mock_worker(self) -> bool: return self.USE_MOCK_WORKER
  def use_mock_blob(self) -> bool: return self.USE_MOCK_BLOB
  ```

  > **service の DB 接続**：result を service が Cloud SQL に直接書き込むため、service の Settings は
  > `DATABASE_URL`（+ 本番は Cloud SQL コネクタ / Unix ソケット接続）を必要とする。api と同じ DB を
  > 指し、issue-017 が `service` の Cloud Run に `DATABASE_URL` と Cloud SQL 接続を注入する。
  > マイグレーションは api のみが実行する（service は DML のみ）。

  > **ロケーション既定の統一**：既存 `GOOGLE_CLOUD_LOCATION` の既定は `us-central1` だが、
  > issue-017 の `region` 既定は `asia-northeast1`。Cloud Tasks キュー / GCS と
  > Vertex AI のリージョンを割らないため、`GOOGLE_CLOUD_LOCATION` の既定を `asia-northeast1` へ
  > 更新し、キューも同じ値を共用する（issue-015 / 017 / 018 と整合させること）。

- [ ] `api/app/services/mock_worker.py` — `MockTaskDispatcher` に積まれたタスクを拾い、
      `service` の `process_fn` を **同一プロセス内で**実行し、結果を **api の DB セッションで
      `Job` 行に直接書き込む**（本番で service が DB 直書きするのと同じ更新を mock-worker が肩代わり）。
      `app_ref` の `mock_worker.py` のバックグラウンドループを踏襲するが、result publisher / push
      ハンドラ呼び出しは無く、Job 更新を直接行う
- [ ] `api/app/main.py` の lifespan で、`settings.use_mock_worker()` の時のみ
      `asyncio.create_task(run_mock_worker(...))` を起動する（`app_ref` の `main.py` lifespan 踏襲。
      本番経路ではポーリングループは一切起動しない）
- [ ] （任意）Cloud Tasks エミュレータの起動手順を `docs/guides/` に追記する開発フローを記す
      （Cloud SQL は既存の docker-compose Postgres をそのまま利用するため追加手順は不要）

### テスト

- [ ] `api/tests/test_mock_task_dispatcher.py` — `dispatch` でタスクが積まれ、`dedup_key`
      重複時に 1 件に畳まれること
- [ ] `api/tests/test_echo_end_to_end.py` — mock-worker 経由で `echo` ジョブを enqueue →
      mock-worker が DB の Job を更新し `QUEUED → COMPLETED` に遷移、`GET /api/v1/jobs/{id}` の
      `result_data.echoed` が一致すること
- [ ] `api/tests/test_enqueue_spillover.py` — `_MAX_TASK_REQUEST_BYTES` 超の payload が
      `MockBlobClient` にスピルし、Job.payload が `{"$requestRef": "gs://..."}` になること
- [ ] `service/tests/test_tasks_handler.py` — `/tasks/{pipeline}` ハンドラが Job を `COMPLETED`
      に書き込むこと・**冪等性**（既に `COMPLETED` の Job への重複配信を 2xx でスキップ）・
      恒久失敗で `Job=FAILED` + 2xx を返すこと
- [ ] `service/tests/test_pipelines.py` — `echo` / `ping` の `process_fn` 単体

## 完了条件

- api が `echo` ジョブを `enqueue_job` で投入すると、Job が DB に `QUEUED` で永続化される
- ローカル（`USE_MOCK_WORKER=true`）では mock-worker が処理し、本番では `service` の
  `POST /tasks/{pipeline}` が処理する（同一の `process_fn`）
- **api に push 受信エンドポイントは存在しない**。`service`（本番）/ mock-worker（ローカル）が
  Cloud SQL の `Job` 行を直接 `COMPLETED` + `result_data` に更新する
- 同一 Job への重複配信（Cloud Tasks の at-least-once）に対し、service が**冪等**に振る舞う
  （既に `COMPLETED` ならスキップ）
- `GET /api/v1/jobs/{id}` に最新状態（`status` / `result_data.echoed`）が反映され、
  `status === "COMPLETED"` を返す
- `_MAX_TASK_REQUEST_BYTES` を超える request が GCS にスピルし、メッセージは
  `$requestRef` のみを載せる
- ローカルスタックが **GCP 接続なし**（mock）で end-to-end 起動する
- **コード・設定・ドキュメントが Pub/Sub リソース（トピック / サブスク / push / DLQ /
  `RESULTS_TOPIC` / `PUBSUB_PUSH_SA`）を一切参照しない**
- 品質ゲートが通る：
  - `cd backend && uv run pytest`
  - `cd backend && uv run ruff check && uv run ruff format --check`
  - `cd backend && uv run ty check`
  - `cd frontend && bun run check`（Job ポーリングの Zod スキーマ・client を足す場合）

## 技術詳細

### シーケンス図（api → Cloud Tasks → service →（service が Cloud SQL に Job + 結果を直書き）→ フロントが GET /jobs/{id} をポーリング）

```
Frontend          api (Cloud Run)          Cloud Tasks         service (Cloud Run)        Cloud SQL          GCS
   |  POST enqueue     |                         |                     |                     |               |
   |------------------>| enqueue_job            |                     |                     |               |
   |                   | Job=QUEUED ----------------------------------------------------------->               |
   |                   | (>90KB?) upload --------------------------------------------------------------------->|
   |                   | dispatch(pipeline) ---->| create HTTP task    |                     |               |
   |   {jobId} 202     |                         |                     |                     |               |
   |<------------------|                         |                     |                     |               |
   |                   |                         | POST /tasks/echo    |                     |               |
   |                   |                         |  (OIDC)  ---------->| verify OIDC         |               |
   |                   |                         |                     | Job 引く/冪等チェック <--------------->|
   |                   |                         |                     | Job=PROCESSING ------>               |
   |                   |                         |                     | resolve $requestRef <-(download)------|
   |                   |                         |                     | process_fn(echo)    |               |
   |                   |                         |                     | Job=COMPLETED        |               |
   |                   |                         |                     |  + result_data ----->               |
   |                   |                         |                     |   2xx ack           |               |
   |  GET /jobs/{id}   |                         |                     |                     |               |
   |------------------>| SELECT Job <-------------------------------------------------------->|               |
   |  {status,result}  | Job(status=COMPLETED, result_data) ──> 200    |                     |               |
   |<------------------| （COMPLETED になるまでフロントがポーリング）   |                     |               |
```

### request = Cloud Tasks / result = service が Cloud SQL 直書き（Pub/Sub 不使用）

| 観点 | request（api → service） | result（service → DB） |
|---|---|---|
| 方式 | **Cloud Tasks**（HTTP ターゲット `service` の `/tasks/{pipeline}`） | **service が Cloud SQL の `Job` 行を直接更新** |
| 配信モデル | 点対点（1 タスク = 1 ターゲット URL） | キュー / トピックを介さず DB へ書き込み |
| リトライ/バックオフ | キュー設定（`maxAttempts` / `minBackoff`） | service が一時失敗時に 5xx を返し Cloud Tasks に再試行させる |
| レート制御 | `maxDispatchesPerSecond` / `maxConcurrentDispatches` | （該当なし。書き込みは同期） |
| 重複排除 / 冪等 | `task.name`（dedup_key）で一意化 | service が `Job.status` を確認し冪等化（at-least-once 対策） |
| 認証 | タスクごとの OIDC トークン | service の DB 接続（Cloud SQL コネクタ + IAM / 認証情報） |
| 参考実装の対応 | Azure Queue **request** キュー | Azure Queue **result** キュー（長ポーリング → DB 直書きに置換） |

> **なぜ Pub/Sub を使わないか**：完了結果の消費者は **api（DB）1 つのみ**で点対点であり、
> ファンアウト（1 メッセージ → N サブスク）が不要。service が同じ Cloud SQL に直接書けば、
> トピック / サブスク / push エンドポイント / Dead-letter / OIDC push 検証という一連の機構を
> すべて省け、フロントは `GET /jobs/{id}` のポーリングだけで完了を観測できる。
> 将来 **複数の独立コンシューマ**や**イベント駆動のファンアウト**（例：完了を契機に別系統の
> 通知・集計を非同期で走らせる）が必要になった時点で、Pub/Sub を再導入する。

> **定期スキャン（自律エージェントの定期再スキャン）は将来の専用 issue で実装する。** 起動は
> **Cloud Scheduler → HTTP（Cloud Run / Functions を OIDC で直叩き）を第一候補**とし、
> 仕様書（`仕様書.md` §974「毎週・毎日エージェントが自律的に動く」/ §355「30 日後の再スキャン」/
> §801「Cloud Functions｜定期スキャン｜Pub/Sub トリガー」）準拠で **Pub/Sub → Cloud Functions** も
> 選択肢となる。**本 issue では実装しない。**

### request ペイロード schema（キューを跨ぐので camelCase）／ result（DB の `Job.result_data`）

```jsonc
// Cloud Tasks body（小ペイロード）
{ "jobId": "f1c2...", "jobType": "echo", "message": "hello" }

// Cloud Tasks body（GCS スピル）。バケット名は issue-017 の命名規約
//   gs://<project_name>-<environment>-job-payloads/...（例: fullstack-app-stg-job-payloads）
{ "jobId": "f1c2...", "jobType": "echo", "$requestRef": "gs://fullstack-app-stg-job-payloads/requests/echo/f1c2....json" }

// result はキュー/メッセージを介さず、service が Job.result_data（JSONB, camelCase）に直接書く
// 例: GET /api/v1/jobs/{id} のレスポンス（Job 行の投影）
{ "id": "f1c2...", "type": "echo", "status": "COMPLETED", "resultData": { "echoed": "hello" }, "errorMessage": null }
```

### `gs://` 参照フォーマット

```
gs://{bucket}/{object_path}
  requests/{pipeline}/{job_id}.json   # api → service の大 request（result は DB 直書きのため GCS スピルなし）
```

`shared/shared/gcs.py`：

```python
def parse_gcs_url(url: str) -> tuple[str, str]:
    """gs://bucket/object/path → (bucket, object/path)."""
    if not url.startswith("gs://"):
        raise ValueError(f"Not a gs:// URL: {url}")
    rest = url[len("gs://"):]
    slash = rest.find("/")
    if slash <= 0:
        raise ValueError(f"Invalid gs:// URL (missing object path): {url}")
    return rest[:slash], rest[slash + 1 :]
```

### Job 状態遷移

```
            enqueue_job()               /tasks/{pipeline} 受理        process_fn 完了（service が DB 直書き）
   (none) ───────────────> QUEUED ───────────────────────> PROCESSING ──────────────────> COMPLETED
                              │                                  │
                              │ (mock-worker / service が拾う)    │ process_fn 恒久失敗 → service が Job=FAILED
                              │                                  ├──────────────────────> FAILED
                              │                                  │ stale タイムアウト掃除（api）→ FAILED
                              │                                  └──────────────────────> FAILED
                              └─ cancel(将来) ──> CANCELLED
```

- `QUEUED → PROCESSING`：service が `/tasks/{pipeline}` を受理し処理開始した時点で、
  service が自前の DB セッションで `status=PROCESSING` + `started_at` を書く
- `PROCESSING → COMPLETED / FAILED`：service が処理完了 / 恒久失敗時に DB を直接更新して確定
- 古い `PROCESSING` の救済（`app_ref` の `_timeout_stale_jobs` 相当）は **api 側の
  `timeout_stale_jobs`** で行う（service クラッシュ等で `PROCESSING` のまま放置された Job を
  `FAILED` 化）。一時失敗は service が 5xx を返して Cloud Tasks に再試行させ、最大試行超過で
  放置となったものをこの掃除が回収する

### ローカル mock フロー（GCP なし）

```
api プロセス（lifespan 内）
  ├─ MockTaskDispatcher  ← enqueue_job が dispatch()
  ├─ run_mock_worker()（asyncio.create_task）
  │     while True:
  │       task = dispatcher.pop()
  │       request_model, result_model, process_fn = PIPELINES[task.pipeline]
  │       result = await process_fn(request, ctx)   # service の process_fn を import して直呼び
  │       # 本番で service が DB に書くのと同じ更新を mock-worker が肩代わり
  │       Job(jobId).status = COMPLETED; Job.result_data = result  # api の DB セッションで直接更新
  └─ GET /jobs/{id} が COMPLETED を返す
```

`USE_MOCK_QUEUE=false` にすると `CloudTasksDispatcher` + 実 `service` 経路へ切り替わる
（`get_task_dispatcher()` の分岐は `app_ref` の `get_queue_client()` と同型）。

### 環境変数表

| 変数 | 既定（dev） | 用途 |
|---|---|---|
| `USE_MOCK_QUEUE` | `true` | in-memory dispatcher を使う（GCP 不要） |
| `USE_MOCK_WORKER` | `true` | api 内で mock-worker を起動して service を肩代わり |
| `USE_MOCK_BLOB` | `true` | in-memory blob でスピルを模擬 |
| `SERVICE_TASKS_URL` | `http://localhost:8001` | Cloud Tasks の HTTP ターゲット（service）。issue-017 が service の URL を注入 |
| `TASKS_INVOKER_SA` | `""` | Cloud Tasks → service を呼ぶ OIDC SA（issue-017） |
| `GOOGLE_CLOUD_PROJECT` | `""` | Cloud Tasks / GCS のプロジェクト（**既存・Vertex AI と共用**） |
| `GOOGLE_CLOUD_LOCATION` | `asia-northeast1` | Cloud Tasks / Vertex AI のロケーション（**既存キーを共用**。既定を `asia-northeast1` に更新） |
| `TASKS_QUEUE` | `job-requests` | request キュー名（issue-017 で作成） |
| `JOB_PAYLOAD_BUCKET` | `""` | スピルオーバー用 GCS バケット（issue-017 の `*-job-payloads` を outputs から注入） |
| `DATABASE_URL`（service） | （api と同一 DB） | result 直書き用。service の Cloud Run に Cloud SQL 接続とともに注入（issue-017） |

> シークレットは **Secret Manager** で注入（CLAUDE.md：プレーンテキスト環境変数は禁止）。
> 上記の SA / プロジェクト ID は機微ではないが、本番値は issue-017 の Terraform 出力から渡す。
> キー名は issue-017 の `cloud-run.tf` 注入名と一字一句一致させること（不一致は起動時クラッシュ）。

### 依存パッケージ（`api` / `service`）

| パッケージ | 配置 | 用途 |
|---|---|---|
| `google-cloud-tasks` | `api` | `CloudTasksDispatcher` |
| `google-cloud-storage` | `shared` / 両方 | `GcsBlobClient` |
| `google-auth` | `service` | Cloud Tasks タスクの OIDC 検証（`id_token.verify_oauth2_token`） |
| `sqlmodel` / `pydantic>=2` | `shared` | `Job` モデルと共通スキーマ（統合クライアントは置かない） |
| DB ドライバ（asyncpg + SQLAlchemy async） | `service` | result の Cloud SQL 直書き（`service/service/db.py`） |

## 参考

- 参考実装（Azure → GCP に写経した出所）
  - `app_ref/services/api/app/services/interfaces.py` — `QueueClient` / `BlobClient` Protocol →
    `shared/shared/queue.py` の `TaskDispatcher` / `BlobClient`（result publisher は持たない）
  - `app_ref/services/api/app/services/azure_queue_client.py` /
    `app_ref/services/api/app/services/mock_queue_client.py` — 実 / mock クライアントの対構造
  - `app_ref/services/api/app/services/dependencies.py` — `get_queue_client` / `is_mock_queue` /
    `get_blob_client` の切替パターン → `get_task_dispatcher` / `get_blob_client`
  - `app_ref/services/api/app/services/workflow_orchestrator.py` — `enqueue_job`（スピル判定・
    `$requestRef`・48KB 上限） → `job_orchestrator.enqueue_job`
  - `app_ref/services/api/app/services/result_poller.py` — `_persist_job_status`（result の
    **DB 永続化**）/ `_timeout_stale_jobs` → DB 永続化は **service の `/tasks/{pipeline}` ハンドラが
    直接担う**、stale 掃除は api の `timeout_stale_jobs`。`process_result` / `_HANDLERS` /
    `_resolve_blob_ref`（result 側）は本設計では不要（result はキューを介さない）
  - `app_ref/services/api/app/services/mock_worker.py` — バックグラウンドで Job を進行させる →
    `api/app/services/mock_worker.py`（結果は api の DB セッションで Job を直接更新）
  - `app_ref/services/api/app/main.py` — lifespan で poller / mock-worker を起動 → mock-worker のみ
  - `app_ref/services/worker/worker/main.py` — `_poll_queue` / `_resolve_request_ref` /
    ack セマンティクス → `POST /tasks/{pipeline}`（ハンドラ参照として維持。結果は publish せず
    DB 直書き）
  - `app_ref/services/worker/worker/broker.py` — `kick` / `listen` / `acknowledge`（Azure Queue
    長ポーリング、本設計では Cloud Tasks の HTTP push に置換。`publish_result` は不使用）
  - `app_ref/services/worker/worker/registry.py` — `PIPELINES` dict と
    `request_queue` / `result_queue` 命名 → `service/service/registry.py`
  - `app_ref/services/worker/worker/context_factory.py` /
    `app_ref/services/worker/worker/context.py` — `PipelineContext` → `service/service/context.py`
  - `app_ref/services/functions/functions/function_app.py` /
    `app_ref/services/functions/host.json` — queue trigger / `maxDequeueCount` / `visibilityTimeout`
    （= Cloud Tasks の `maxAttempts` / ack 期限の発想元。定期スキャンの実装は将来の専用 issue）
  - `app_ref/services/shared/shared/blob.py` — `parse_blob_url` → `shared/shared/gcs.py`
    の `parse_gcs_url`
  - `app_ref/services/shared/shared/enums.py` — `JobType` / `JobStatus` / `ResultStatus`（`StrEnum`）→
    `shared/shared/enums.py`
  - `app_ref/services/shared/shared/schemas/base.py` — `SharedBaseModel`（camelCase エイリアス）→
    `shared/shared/schemas/base.py`
- 現行コード（変更対象）
  - `backend/app/core/config.py` — 設定追加先（`USE_MOCK_QUEUE` 等）。現状はキュー設定なし・
    AI は Vertex AI（`GOOGLE_CLOUD_PROJECT` + ADC、API キーなし）
  - `backend/app/main.py` — lifespan で mock-worker を起動（現状は DB engine dispose のみ）
- 関連 Issue（相互参照）
  - **issue-015**（`docs/issue/015-backend-api-service-split-monorepo.md`） — 前提。
    `shared` / `api` / `service` の uv workspace 構成・`backend/` を workspace ルートに残す判断
  - **issue-017**（`docs/issue/017-terraform-gcp-infrastructure.md`） — 本 issue が使う
    Cloud Tasks キュー / GCS バケット / SA・OIDC / service の Cloud SQL 接続（`DATABASE_URL` 注入）を
    Terraform でプロビジョン（`infra/gcp` + `infra/bootstrap/gcp`、`infra/azure`・`infra/aws` の規約踏襲）
  - **issue-018**（`docs/issue/018-stack-analysis-async-job-on-service.md`） — 本基盤の上に
    ADK スタック解析を `STACK_ANALYSIS` パイプラインとして載せる（`echo` / `ping` を本物に差し替え）
- 規約
  - `CLAUDE.md` — GCP 必須サービス（Cloud Run / Cloud Functions / Cloud SQL / Secret Manager /
    Artifact Registry / Workload Identity Federation / Cloud Armor）、Python は snake_case・
    4 スペース・120 桁、PATCH を更新に使う、ruff / ty / pytest ゲート、`CHANGELOG.md`（日本語）
