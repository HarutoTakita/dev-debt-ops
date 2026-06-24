# バックエンドを api / service コンテナに分割する（uv workspace モノレポ化）

## 概要

現状のバックエンドは単一の FastAPI モノリス（`backend/app/`、worker なし・キューなし・Job
モデルなし）である。本 issue では **挙動を一切変えずに**、`backend/` を uv workspace
（メンバー: `shared` / `api` / `service`）へ再編し、**api コンテナ** と **service コンテナ**
の 2 コンテナで起動できる土台を作る。

- **api**（= Cloud Run サービス、外部公開）: 既存 `backend/app/` をそのまま `backend/api/app/`
  へ移設したもの。エンドポイント・認証・SPA 配信の挙動は不変。
- **service**（= 重い処理 worker。参考実装の `worker` に相当）: `/health` と
  `/tasks/{pipeline}` の **スタブのみ** を持つ新規 FastAPI スケルトン。実処理は後続 issue。
- **shared（共有データ層）**: enum・共有 pydantic スキーマ・キュー / Blob クライアントの
  Protocol・**共有 ORM モデル（SQLModel）＝ `Job`** の **置き場所**（中身の実装・実配線は
  016）。**統合クライアント（github / gemini / httpx / PyJWT）は引き続き shared に置かない**
  — これらは api / service それぞれが必要に応じて持つ（既存方針を維持）。

参考実装 `app_ref/services/`（uv workspace: `shared` / `api` / `worker` / `functions`）の
構成を踏襲するが、本リポジトリは `backend/` が CI・docker・CLAUDE.md・docs から多数参照される
ため、トップレベル `services/` を新設せず **`backend/` をワークスペース・ルートとして残す**
（churn 最小化。詳細は「## 技術詳細 ▸ なぜ `backend/` を workspace ルートにするか」）。

本 issue は **フォルダ構成変更そのもの（ユーザーの主目的）** であり、キュー実装（Cloud Tasks /
GCS スピルオーバー）は後続 issue-016 に委ねる。

## 背景・目的

### 現状（単一モノリス）

現状の `backend/` ツリーは uv の単一プロジェクト（`backend/pyproject.toml` の `[project]
name = "backend"`）であり、以下の構成になっている：

```
backend/
  pyproject.toml          # [project] name = "backend" 単一パッケージ
  uv.lock
  alembic.ini             # script_location = %(here)s/app/alembic
  app/
    main.py               # FastAPI app + SPAStaticFiles マウント
    api/v1/router.py      # /api/v1 配下の全ルータを集約
    api/{deps,docs}.py
    core/{config,db,security,...}.py
    models/ schemas/ services/ agent/ scripts/
    alembic/{env.py, versions/0001..0003}
  tests/
```

- `docker/Dockerfile.dev`・`docker/Dockerfile.prod` はいずれも単一 `backend/app` を前提。
- `compose.yml` は `backend` + `db`(+`pgadmin`) の 3 サービス。
- `.github/workflows/ci.yml` は `cd backend && uv sync --frozen` → ruff / ty / pytest を実行。
- worker / キュー / Job モデルは存在しない。重い処理（ADK スタック解析）も api プロセス内で同期実行。

### 目的

1. **api と service の 2 コンテナに物理分割** し、重い処理を service 側へ寄せられる土台を作る
   （実際の非同期化は 016 / 018）。
2. **uv workspace モノレポ化** で `shared` を api / service の双方から再利用可能にする
   （enum・Protocol・共有スキーマの単一ソース化）。
3. 既存エンドポイント・認証・SPA 配信・テストの **挙動は完全に不変** に保つ
   （本 issue はリファクタリングであり機能追加ではない）。

### 前提 Issue（depends_on）

- **なし（基盤 issue）**。本 issue は後続の 016 / 017 / 018 すべての土台となる。

後続 issue との関係：

| Issue | 内容 | 本 issue への依存 |
|---|---|---|
| **016** `016-async-task-queue-cloud-tasks.md` | Cloud Tasks による api→service 非同期タスク基盤・Job ライフサイクル（service が Cloud SQL に結果を直接書き込み）・GCS スピルオーバー・ローカル mock/エミュレータ | 015（workspace と service スケルトン） |
| **017** `017-terraform-gcp-infrastructure.md` | GCP 版 Terraform（`infra/gcp` + `infra/bootstrap/gcp`） | 015（コンテナ構成）, 016（キュー） |
| **018** `018-stack-analysis-async-job-on-service.md` | ADK スタック解析を service へ移し非同期ジョブ化 | 015, 016 |

### このプロジェクトの GCP マッピング（後続 issue の前提・本 issue では実装しない）

本 issue は構成変更のみだが、service の `/tasks/{pipeline}` スタブが将来どう呼ばれるかの
前提を共有設計として明記しておく（実装は 016 / 017）：

- **api コンテナ** = Cloud Run サービス（外部公開・HTTPS LB + Cloud Armor の背後）。
- **service コンテナ** = Cloud Run サービス（ingress=internal、Cloud Tasks から OIDC 認証付き
  HTTP で `/tasks/{pipeline}` を起動。高 CPU/メモリ・長タイムアウト）。
- **api→service タスク依頼** = **Cloud Tasks**（HTTP ターゲット = service の `/tasks/{pipeline}`、
  OIDC トークン、リトライ/バックオフ）。参考実装の Azure Queue request キュー相当。
- **service→api 結果通知** = **無し（service が Cloud SQL に直接書き込み）**。service の
  `/tasks/{pipeline}` ハンドラが処理完了後、自前の DB セッションで `Job` 行を
  `COMPLETED` / `FAILED` + `result_data` に更新し、ドメイン結果も書く。フロントは
  `GET /api/v1/jobs/{job_id}` をポーリングするだけ（api へのコールバックは無い）。
- **大きいペイロード** = **Cloud Storage (GCS)** へスピルオーバーし `$requestRef`
  を載せる（参考実装の `blob://` 相当。request payload 用に継続）。
- **定期スキャン（自律エージェントの定期再スキャン）は将来の専用 issue で実装**。起動は
  **Cloud Scheduler → HTTP（Cloud Run / Functions を OIDC で直叩き）を第一候補**、
  仕様書（`仕様書.md` §974「毎週・毎日エージェントが自律的に動く」/ §355「30 日後の再スキャン」/
  §801「Cloud Functions｜定期スキャン｜Pub/Sub トリガー」）準拠で **Pub/Sub → Cloud Functions**
  も選択肢。**本 issue（015–018）では実装しない**。

> 本 issue ではこれらは **コメント・スタブ・Protocol の置き場所** に留め、実配線は 016 で行う。

## タスク

### 1. uv workspace ルート（`backend/pyproject.toml`）

- [ ] `backend/pyproject.toml` を **ワークスペース・ルート** に書き換える
      （`[tool.uv.workspace] members = ["shared", "api", "service"]`。将来 `functions` を追加可能に
      コメントで明記。app_ref/services/pyproject.toml を踏襲）
- [ ] ルート `[project]` は集約用に `name = "rosetta-backend"` 等へ改名し、`requires-python = ">=3.13"`
      のみ持たせる（現行の依存はすべて `api/` 配下へ移す）
- [ ] ルートに `ruff` 設定を集約（`line-length = 120`、`target-version = "py313"`、現行の
      `select` / `pydocstyle` / `per-file-ignores` / `flake8-bugbear` をそのまま移植）。
      各メンバーはルート設定を継承する
- [ ] ルートに `[dependency-groups] dev`（`pytest` / `pytest-asyncio` / `pytest-cov` /
      `pytest-mock` / `ruff` / `ty`）を集約し、全メンバーで共有
- [ ] `backend/uv.lock` を `uv lock` で再生成（workspace 全メンバーを 1 ロックに解決）
- [ ] `backend/.python-version`（`3.13`）はルートに残す

### 2. shared パッケージ新設（`backend/shared/`）

> 中身（実装）は 016 が担う。本 issue では **パッケージとビルド設定 + 置き場所** を作るところまで。

- [ ] `backend/shared/pyproject.toml`（hatchling ビルド、`[tool.hatch.build.targets.wheel]
      packages = ["shared"]`。app_ref/services/shared/pyproject.toml を踏襲。依存は
      `pydantic>=2` + `sqlmodel`。**統合クライアント（github / gemini / httpx / PyJWT）は
      shared に置かない** — これらは api / service 各自が持つ）
- [ ] `backend/shared/shared/__init__.py`
- [ ] `backend/shared/shared/enums.py` — `JobType` / `JobStatus` の `StrEnum`（app_ref の
      `shared/enums.py` を踏襲。DevDebtOps 用に `JobType.STACK_ANALYSIS` 等を定義。
      `JobStatus` の値は **大文字**（QUEUED / PROCESSING / COMPLETED / FAILED / CANCELLED）。
      値の確定・拡張は 016 / 018）
- [ ] `backend/shared/shared/queue.py` — キュー / Blob クライアントの **Protocol** を置く枠
      （`TaskQueue` / `BlobStore` 等の `typing.Protocol`。実装クラスは 016 で Cloud Tasks /
      GCS 向けに追加）
- [ ] `backend/shared/shared/schemas/__init__.py` + `backend/shared/shared/schemas/base.py` —
      共有 pydantic 基底スキーマ（`PipelineError` 等。app_ref の `shared/schemas/base.py` を踏襲）
- [ ] `backend/shared/shared/models/__init__.py` — 共有 ORM モデルの再エクスポート
      （`from shared.models import Job` で api / service の双方から利用可能にする）
- [ ] `backend/shared/shared/models/job.py` — `Job`（SQLModel `table=True`）。api / service
      双方が共有する Job ライフサイクルの単一ソース（`id` / `job_type` / `status`
      （`JobStatus`、大文字）/ `payload` / `result_data` / `error` / タイムスタンプ等）。
      **Alembic マイグレーションと DB エンジン / セッション生成は api が所有**（`api/app/core/db.py`）。
      service は自前の薄い `service/service/db.py` で shared モデルに DML するのみ
      （マイグレーションは実行しない）。フィールドの確定は 016 / 018
- [ ] `backend/shared/tests/test_enums.py` — enum の最小スモークテスト（パッケージとして
      `uv run pytest` が通ることの担保）

### 3. 既存 `backend/app/` を `backend/api/` へ移設

- [ ] `backend/app/` → `backend/api/app/` へディレクトリ移動（`git mv` で履歴保持）
- [ ] `backend/alembic.ini` → `backend/api/alembic.ini` へ移動（`script_location =
      %(here)s/app/alembic` は相対のため移動後も整合。`prepend_sys_path = .` も維持）
- [ ] `backend/app/alembic/` は `backend/api/app/alembic/` として一緒に移動（`env.py`・
      `versions/0001..0003` を含む。リビジョン ID は変更しない）
- [ ] `backend/tests/` → `backend/api/tests/` へ移動
- [ ] `backend/api/pyproject.toml` を新設（`[project] name = "rosetta-api"`、現行 `backend`
      の全 `dependencies` を移植。`[tool.uv.sources] rosetta-shared = { workspace = true }` で
      shared を配線し、`dependencies` に `"rosetta-shared"` を追加。`[tool.pytest.ini_options]
      asyncio_mode = "auto"`, `testpaths = ["tests"]`）
- [ ] import パスは **変更不要**（`app.*` 名前空間は維持。`from app.core.config import settings`
      等はそのまま動く。新パスは `backend/api/app/...`）。移設対応は「## 技術詳細 ▸ 移設対応表」参照
- [ ] **Annotated DI param 順序を保持**（CLAUDE.md）: `backend/api/app/api/deps.py` の
      `Annotated[T, Depends(f)]` 依存パラメータの宣言順序を移設時に変えない。順序変更は pytest
      teardown 中の DROP TABLE で `DeadlockDetectedError` を誘発する

### 4. service スケルトン新設（`backend/service/`）

> `/tasks/{pipeline}` は **スタブ**（202 を返し本文を素通しでログするのみ）。実処理は 018。

- [ ] `backend/service/pyproject.toml`（`[project] name = "rosetta-service"`、依存は
      `fastapi[standard-no-fastapi-cloud-cli]` + `"rosetta-shared"` + `sqlalchemy[asyncio]` +
      `asyncpg`（service が Cloud SQL に Job 結果を直接書き込むため。`sqlmodel` は
      `rosetta-shared` 経由で解決）。`[tool.uv.sources] rosetta-shared = { workspace = true }`）
- [ ] `backend/service/service/__init__.py`
- [ ] `backend/service/service/db.py` — 薄い engine / async session 生成（`DATABASE_URL` を
      読み、`create_async_engine` + `async_sessionmaker`）。**マイグレーションは持たない**
      （DDL は api が Alembic で所有）。service は shared の `Job` モデルに対し DML するのみ。
      本 issue ではスタブ実装（接続設定のみ。実際の Job 更新は 016 / 018）
- [ ] `backend/service/service/main.py` — FastAPI app。`GET /health`（`{"status": "ok"}`、
      api の `health.py` と同形）と `POST /tasks/{pipeline}`（スタブ: ペイロードを受領しログ出力、
      `202 Accepted` を返す。OIDC 検証・Job 状態遷移（`db.py` 経由で shared `Job` を
      `COMPLETED` / `FAILED` に更新）・実パイプライン実行は 016 / 018 の TODO コメント）
- [ ] `backend/service/service/pipelines/__init__.py` — パイプライン置き場（空。018 で `stack_analysis`
      を追加。app_ref の `worker/registry.py` 相当の登録ポイントになる旨をコメント）
- [ ] `backend/service/tests/test_health.py` / `test_tasks.py` — `/health` と `/tasks/{pipeline}`
      スタブの最小テスト（`httpx` + `ASGITransport`）

### 5. Dockerfile（マルチステージ uv workspace ビルド）

- [ ] `docker/api.Dockerfile`（マルチステージ。builder で workspace ルート + shared + api を
      COPY し `uv sync --frozen --no-dev --package rosetta-api`。runtime に `.venv` / `shared` /
      `api/app` / `api/alembic` / `api/alembic.ini` をコピー。**prod の api は SPA を焼き込む**ため
      frontend ビルドステージを残し `frontend build → api/app/static` を維持。
      app_ref/services/api/Dockerfile + 既存 `docker/Dockerfile.prod` の流れを踏襲。
      `CMD` は `alembic upgrade head && uvicorn app.main:app ...`）
- [ ] `docker/service.Dockerfile`（マルチステージ。builder で workspace ルート + shared + service
      を COPY し `uv sync --frozen --no-dev --package rosetta-service`。runtime に `.venv` / `shared`
      / `service/service` をコピー。`CMD` は `uvicorn service.main:app ...`。
      app_ref/services/worker/Dockerfile を踏襲。Playwright 等の heavy 依存は 018 で必要になるまで入れない）
- [ ] dev 用に `docker/api.Dockerfile` / `docker/service.Dockerfile` に dev ステージ（または
      `--reload` 付き dev target）を用意し、`--no-dev` を外して `--reload` 起動（app_ref の
      `api/Dockerfile.dev` / `worker/Dockerfile.dev` を踏襲）。**旧 `docker/Dockerfile.dev` /
      `docker/Dockerfile.prod` は削除**

### 6. compose（api + service + db）

- [ ] `compose.yml` を `api` + `service` + `db`(+`pgadmin`) に更新
  - `api`: `docker/api.Dockerfile`（dev target）、`ports: 8000:8000`、`env_file: .env.dev`、
    `secrets:/app/secrets:ro` マウント維持、`depends_on: db (healthy)`
  - `service`: `docker/service.Dockerfile`（dev target）、`env_file: .env.dev`、`depends_on: db`
  - **両サービスを `develop.watch` で sync**（`backend/api/app` → `/app/app`、
    `backend/service/service` → `/app/service`、`backend/shared/shared` → `/app/shared/shared`、
    `pyproject.toml` / `uv.lock` 変更時は `rebuild`）。app_ref/docker-compose.dev.yml を踏襲
  - `db`（`pgvector/pgvector:pg17`）・`pgadmin`（`profiles: [tools]`）は現状維持
- [ ] `compose.prod.yml` を `api`(3 レプリカ, Traefik) + `service`(N レプリカ) + `db` に更新
  - `api`: `docker/api.Dockerfile`、`deploy.replicas: 3`、既存の Traefik ラベル
    （`PathPrefix(/)`・auth/login 5/min・10/hour・auth/refresh 30/min のレート制限）を **そのまま維持**
  - `service`: `docker/service.Dockerfile`、`deploy.replicas: 2`（Traefik では公開しない —
    本番は Cloud Run internal + Cloud Tasks。ローカルでは api から内部ネットワーク経由で到達）
  - `db` / `traefik` は現状維持
- [ ] `.env.dev` / `.env.example` に service 用の新規キー枠（後続 016 用のプレースホルダ。
      本 issue では未使用でも `extra="ignore"` で無害）を追記してよい

### 7. CI（`.github/workflows/ci.yml`）

- [ ] `check-backend` を **メンバー単位** に分割（matrix もしくは個別 job）：
      `shared` / `api` / `service` それぞれで `uv sync --frozen` → `ruff check` →
      `ruff format --check` → `uv run ty check`
- [ ] `test-backend` を **メンバー単位** に分割：`shared` / `api` / `service` それぞれで
      `uv run pytest`（api は従来どおり Postgres サービスコンテナ + `DATABASE_URL` 必須。
      shared / service は DB 不要）
- [ ] `cache-dependency-glob` を `backend/uv.lock`（workspace 単一ロック）に維持
- [ ] workspace ルートでまとめて検証する場合は `cd backend && uv run --package rosetta-api ...`
      のように `--package` で対象を絞れる旨をコメント
- [ ] CLAUDE.md の **Annotated DI param 順序** 注意点を CI レビュー観点として PR 説明に残す

### 8. ドキュメント

- [ ] `CLAUDE.md` の「モノレポ構成」「バックエンド (`backend/`)」節を本構成（uv workspace:
      shared / api / service、2 コンテナ、`docker/api.Dockerfile` / `docker/service.Dockerfile`）に更新
- [ ] バックエンドの開発・テスト・リントコマンドを workspace 版へ更新
      （例: `cd backend && uv run --package rosetta-api pytest`）
- [ ] `docs/reference` にモノレポ構成の参照ページを追加（または follow-up として明記）

## 完了条件

- `docker compose up`（dev）で **`api`(:8000) + `service` + `db`** が起動し、
  `curl localhost:8000/api/v1/health` が `{"status":"ok"}` を返すこと
- service コンテナで `GET /health` が `{"status":"ok"}`、`POST /tasks/{any}` が `202 Accepted`
  を返すこと（スタブ。実処理なし）
- `docker compose -f compose.prod.yml up --build` で api 3 レプリカ + service + Traefik が起動し、
  `http://localhost:8080` で **ビルド済み SPA と `/api` の両方** が配信されること（既存挙動不変）
- 各メンバーで `uv run --package <pkg> pytest` が通ること（`rosetta-shared` / `rosetta-api` /
  `rosetta-service`）。既存 api テストは **すべて pass**（挙動不変の証明）
- `from shared.models import Job` が api / service の双方からインポートできること
  （Job モデルは shared に置き、DDL / マイグレーションは api 所有）。service の `db.py` が
  `DATABASE_URL` から async engine を構築できること（実 DML は 016 / 018）
- `cd backend && uv run ruff check` / `uv run ruff format --check` / `uv run ty check` が
  全メンバーで通ること
- 既存エンドポイント（`/api/v1/auth/*`・`/api/v1/orgs/*`・`/api/v1/github/*`・
  `/api/v1/stack/*`・`/api/v1/health`）の **挙動・パス・レスポンスが不変** であること
- `frontend` 側は **無変更**（api のパス・プロキシ先 `/api` は変わらない）。`bun run check` が通ること
- CI（`.github/workflows/ci.yml`）が shared / api / service の lint・type・test を実行し緑になること
- Alembic マイグレーションがリビジョン ID 不変で `alembic upgrade head` 成功すること

## 技術詳細

### 目標ツリー

```
backend/
  pyproject.toml            # [tool.uv.workspace] members = ["shared","api","service"]
  uv.lock                   # workspace 全メンバーを 1 ロックに解決
  .python-version           # 3.13

  shared/
    pyproject.toml          # hatchling, packages = ["shared"], deps = pydantic>=2 + sqlmodel
    shared/
      __init__.py
      enums.py              # JobType / JobStatus (StrEnum, 値は大文字)  ← 016 で確定
      queue.py              # TaskQueue / BlobStore Protocol（枠）  ← 016 で実装
      schemas/
        __init__.py
        base.py             # PipelineError 等の共有基底スキーマ
      models/
        __init__.py         # from shared.models import Job
        job.py              # Job (SQLModel, table=True) ← api/service 双方で共有  ← 016/018 で確定
    tests/
      test_enums.py

  api/
    pyproject.toml          # name = rosetta-api, deps = 旧 backend の全依存 + rosetta-shared
    alembic.ini             # ← backend/alembic.ini から移設
    app/                    # ← backend/app/ をそのまま移設（app.* 名前空間は不変）
      main.py
      api/v1/router.py
      core/ models/ schemas/ services/ agent/ scripts/
      alembic/{env.py, versions/0001..0003}
      static/               # prod のみ: frontend build 成果物を焼き込む（既存挙動）
    tests/                  # ← backend/tests/ を移設

  service/
    pyproject.toml          # name = rosetta-service, deps = fastapi + rosetta-shared
                            #   + sqlalchemy[asyncio] + asyncpg（Cloud SQL に Job 結果を直書き）
    service/
      __init__.py
      db.py                 # 薄い engine/async session（DATABASE_URL）。DDL/マイグレーションは持たない
      main.py               # FastAPI: GET /health + POST /tasks/{pipeline}（スタブ）
      pipelines/
        __init__.py         # 018 で stack_analysis を登録（app_ref worker/registry.py 相当）
    tests/
      test_health.py
      test_tasks.py

docker/
  api.Dockerfile            # マルチステージ uv workspace（builder→runtime, prod は SPA 焼き込み）
  service.Dockerfile        # マルチステージ uv workspace（builder→runtime）
```

### なぜ `backend/` を workspace ルートにするか（app_ref の `services/` を採らない理由）

app_ref はトップレベル `services/`（`services/api`・`services/worker`・`services/shared`）を
ワークスペース・ルートにしている。本リポジトリは異なる判断を採る：

- `backend/` は **CI（`ci.yml` の `cd backend`）・docker（`docker/*.Dockerfile` の
  `COPY backend/...`）・CLAUDE.md・docs から多数参照** されている。トップレベル `services/` へ
  移すと、これらすべての参照を書き換える必要があり churn が大きい。
- `backend/` を workspace ルートに据え、その配下に `shared` / `api` / `service` を置けば、
  外部参照のプレフィックス（`backend/`）はほぼ不変のまま、内部だけをモノレポ化できる。
- よって本 issue では **`backend/` = workspace ルート**、メンバーを `backend/{shared,api,service}`
  とする（この判断は 016 / 017 / 018 すべての前提となる）。

重い処理コンテナの名称は、ユーザー要望に合わせ **`service`** とする（参考実装の `worker`
に相当。Cloud Run サービスとして稼働するため `service` という名が実態にも合う）。

### 移設対応表（旧パス → 新パス。import 名前空間は不変）

| 種別 | 旧パス | 新パス | import への影響 |
|---|---|---|---|
| アプリ本体 | `backend/app/` | `backend/api/app/` | なし（`app.*` のまま） |
| エントリ | `backend/app/main.py` | `backend/api/app/main.py` | `app.main:app` 不変 |
| ルータ集約 | `backend/app/api/v1/router.py` | `backend/api/app/api/v1/router.py` | 不変 |
| DI 依存 | `backend/app/api/deps.py` | `backend/api/app/api/deps.py` | **param 順序維持** |
| 設定 | `backend/app/core/config.py` | `backend/api/app/core/config.py` | 不変 |
| Alembic 設定 | `backend/alembic.ini` | `backend/api/alembic.ini` | `script_location` 相対のため不変 |
| マイグレーション | `backend/app/alembic/` | `backend/api/app/alembic/` | リビジョン ID 不変 |
| テスト | `backend/tests/` | `backend/api/tests/` | `from app...` 不変 |
| プロジェクト定義 | `backend/pyproject.toml`（単一） | `backend/api/pyproject.toml`（メンバー） | 依存を api へ集約 |
| 新規: workspace ルート | — | `backend/pyproject.toml`（`[tool.uv.workspace]`） | ruff/dev を集約 |
| 新規: shared | — | `backend/shared/shared/` | `from shared...`（新規 import の置き場所） |
| 新規: service | — | `backend/service/service/` | `from service...`（新規） |

> ポイント: api は `app.*` 名前空間を維持するため **アプリ側コードの import 書き換えはゼロ**。
> リスクは「物理移動」と「pyproject 分割」「Dockerfile / compose / CI のパス更新」に限定される。

### workspace pyproject 抜粋（app_ref/services/pyproject.toml 踏襲）

```toml
# backend/pyproject.toml（workspace ルート）
[project]
name = "rosetta-backend"
version = "0.0.5"
requires-python = ">=3.13"

[tool.uv.workspace]
members = ["shared", "api", "service"]  # 将来 "functions" を追加

[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC", "DTZ", "RUF", "TID", "PT", "D"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"*/app/alembic/versions/**" = ["D"]
"*/tests/**" = ["D"]

[tool.ruff.lint.extend-per-file-ignores]
"*" = ["D100", "D104", "D105", "D107"]

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["fastapi.Depends"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.1.0",
    "pytest-mock>=3.15.1",
    "ruff>=0.15.12",
    "ty>=0.0.34",
]
```

```toml
# backend/api/pyproject.toml（メンバー）
[project]
name = "rosetta-api"
version = "0.0.5"
requires-python = ">=3.13"
dependencies = [
    "rosetta-shared",
    "alembic>=1.18.4",
    "asyncpg>=0.31.0",
    "fastapi-users[sqlalchemy]>=15.0.5",
    "fastapi[standard-no-fastapi-cloud-cli]>=0.136.1",
    "google-adk>=0.4.0",
    "google-genai>=1.0.0",
    "httpx>=0.28.1",
    "httpx-oauth>=0.15.0",
    "PyJWT>=2.8.0",
    "cryptography>=42.0.0",
    "pydantic-settings>=2.14.1",
    "scalar-fastapi>=1.8.2",
    "sqlalchemy[asyncio]>=2.0.49",
    "sqlmodel>=0.0.38",
    "uuid-utils>=0.14.1",
]

[tool.uv.sources]
rosetta-shared = { workspace = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

```toml
# backend/shared/pyproject.toml（hatchling ビルド。app_ref/services/shared 踏襲）
[project]
name = "rosetta-shared"
version = "0.0.5"
requires-python = ">=3.13"
# 共有データ層: enum・共有 pydantic スキーマ・queue/Blob Protocol・共有 ORM モデル(Job)。
# 統合クライアント(github/gemini/httpx/PyJWT)は shared に置かない。
dependencies = ["pydantic>=2.0", "sqlmodel>=0.0.38"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["shared"]
```

```toml
# backend/service/pyproject.toml（メンバー）
[project]
name = "rosetta-service"
version = "0.0.5"
requires-python = ">=3.13"
dependencies = [
    "rosetta-shared",                                  # Job(SQLModel) / enum / schemas
    "fastapi[standard-no-fastapi-cloud-cli]>=0.136.1",
    "sqlalchemy[asyncio]>=2.0.49",                     # Cloud SQL に Job 結果を直書き
    "asyncpg>=0.31.0",                                 # ← マイグレーションは api 所有
]

[tool.uv.sources]
rosetta-shared = { workspace = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

> 注: `api` は ADK 等を依存に持つが（DI 順序が支配的なため hatchling より単一 パッケージ
> ビルドが素直）、`shared` のみ `[build-system] hatchling` を明示する（app_ref と同じく
> `packages = ["shared"]` でビルド対象を限定する必要があるため）。

### service スケルトン（`/tasks/{pipeline}` はスタブ）

```python
# backend/service/service/main.py
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="DevDebtOps Service", summary="Heavy-processing worker (async pipelines)")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (Cloud Run / compose healthcheck)."""
    return {"status": "ok"}


@app.post("/tasks/{pipeline}", status_code=202)
async def run_task(pipeline: str, request: Request) -> JSONResponse:
    """Cloud Tasks HTTP target (STUB).

    016 で実装: (1) OIDC トークン検証, (2) `$requestRef` を GCS から解決,
    (3) shared.enums.JobType に対応する pipelines/ のハンドラを実行,
    (4) service 自前の db.py セッションで shared.models.Job を COMPLETED/FAILED +
        result_data に直接更新（api へのコールバックは無い。フロントは
        GET /api/v1/jobs/{job_id} をポーリング）。冪等性: 既に COMPLETED ならスキップ。
    本 issue では受領をログし 202 を返すのみ。
    """
    body = await request.body()
    logger.info("task_received pipeline=%s bytes=%d", pipeline, len(body))
    return JSONResponse(status_code=202, content={"accepted": True, "pipeline": pipeline})
```

### Dockerfile 構造（マルチステージ uv workspace）

```dockerfile
# docker/api.Dockerfile
# Stage 1 — Frontend build（prod の SPA 焼き込み。既存 Dockerfile.prod 踏襲）
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# Stage 2 — Build deps（uv workspace: root + shared + api）
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/shared/pyproject.toml ./shared/pyproject.toml
COPY backend/shared/shared/ ./shared/shared/
COPY backend/api/pyproject.toml ./api/pyproject.toml
COPY backend/api/app/ ./api/app/
COPY backend/api/alembic.ini ./api/alembic.ini
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package rosetta-api

# Stage 3 — Runtime
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/shared /app/shared
COPY --from=builder /app/api/app /app/app
COPY --from=builder /app/api/alembic.ini /app/alembic.ini
COPY --from=frontend /app/build /app/app/static
ENV PATH="/app/.venv/bin:$PATH" ENVIRONMENT=prod
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

```dockerfile
# docker/service.Dockerfile（app_ref/services/worker/Dockerfile 踏襲、heavy 依存なし）
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/shared/pyproject.toml ./shared/pyproject.toml
COPY backend/shared/shared/ ./shared/shared/
COPY backend/service/pyproject.toml ./service/pyproject.toml
COPY backend/service/service/ ./service/service/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package rosetta-service

FROM python:3.13-slim
RUN useradd --create-home --uid 1001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/shared /app/shared
COPY --from=builder --chown=appuser:appuser /app/service/service /app/service
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER appuser
EXPOSE 8000
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### compose 抜粋（dev）

```yaml
# compose.yml
services:
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
      target: dev          # --reload 起動の dev ステージ
    ports: ["8000:8000"]
    env_file: .env.dev
    volumes:
      - ./secrets:/app/secrets:ro
    depends_on:
      db: { condition: service_healthy }
    develop:
      watch:
        - { action: sync, path: ./backend/api/app, target: /app/app, ignore: ["__pycache__/", "*.pyc"] }
        - { action: sync, path: ./backend/shared/shared, target: /app/shared/shared, ignore: ["__pycache__/"] }
        - { action: rebuild, path: ./backend/api/pyproject.toml }
        - { action: rebuild, path: ./backend/uv.lock }

  service:
    build:
      context: .
      dockerfile: docker/service.Dockerfile
      target: dev
    env_file: .env.dev
    depends_on:
      db: { condition: service_healthy }
    develop:
      watch:
        - { action: sync+restart, path: ./backend/service/service, target: /app/service, ignore: ["__pycache__/"] }
        - { action: sync+restart, path: ./backend/shared/shared, target: /app/shared/shared, ignore: ["__pycache__/"] }
        - { action: rebuild, path: ./backend/service/pyproject.toml }
        - { action: rebuild, path: ./backend/uv.lock }

  db:
    image: pgvector/pgvector:pg17
    # …現状維持（healthcheck・volume）

  pgadmin:
    image: dpage/pgadmin4
    profiles: [tools]
    # …現状維持
```

```yaml
# compose.prod.yml（抜粋）
services:
  api:
    build: { context: ., dockerfile: docker/api.Dockerfile }
    environment: { ENVIRONMENT: prod }
    deploy: { replicas: 3 }
    labels:
      # …既存 Traefik ラベル（PathPrefix(/) + auth/login 5/min・10/hour + auth/refresh 30/min）
      # を一字一句変えず維持。本番は Cloud Armor が同等ルールを担う（CLAUDE.md）。

  service:
    build: { context: ., dockerfile: docker/service.Dockerfile }
    deploy: { replicas: 2 }
    # Traefik では公開しない。本番は Cloud Run internal + Cloud Tasks（017）。

  traefik: # …現状維持
  db:      # …現状維持
```

### 起動フロー（移設後）

```
docker compose watch                       # api(:8000) + service + db を起動・同期
cd frontend && bun run dev                 # :5173, /api を :8000(api) にプロキシ（不変）

docker compose -f compose.prod.yml up --build
open http://localhost:8080                 # Traefik → api(3 レプリカ) が SPA + /api を配信
                                           # service(2 レプリカ) は内部のみ
```

### service の呼ばれ方（将来。本 issue では未配線）

```
api (Cloud Run, public)
  └─ enqueue → Cloud Tasks (HTTP target, OIDC)
                 └─ POST → service (Cloud Run, internal) /tasks/{pipeline}
                              └─ service が Cloud SQL に直接書き込み
                                   （shared.models.Job を COMPLETED/FAILED + result_data に更新）
front (SPA)
  └─ GET /api/v1/jobs/{job_id} をポーリング（api が DB の Job を返すだけ）
   ※ 大きい request payload は GCS にスピル（$requestRef）
   ※ api への結果コールバック・Pub/Sub push は無し（方式 A: service が DB に直書き）
   ※ この経路の実装は 016、Terraform プロビジョンは 017、stack_analysis 移設は 018
```

## 参考

### このリポジトリ（移設・更新対象）

- `backend/pyproject.toml` — 単一プロジェクト（→ workspace ルートへ）
- `backend/app/main.py` — FastAPI app + `SPAStaticFiles`（→ `backend/api/app/main.py`、挙動不変）
- `backend/app/core/config.py` — pydantic-settings（→ `backend/api/app/core/config.py`）
- `backend/app/api/v1/router.py` — `/api/v1` 集約（→ `backend/api/app/api/v1/router.py`）
- `backend/app/api/v1/health.py` — service の `/health` スタブの形を踏襲
- `backend/app/api/deps.py` — **Annotated DI param 順序を維持**（CLAUDE.md）
- `backend/alembic.ini`（`script_location = %(here)s/app/alembic`、相対）→ `backend/api/alembic.ini`
- `compose.yml` / `compose.prod.yml` — api + service + db へ更新（Traefik レート制限は維持）
- `docker/Dockerfile.dev` / `docker/Dockerfile.prod` — `docker/api.Dockerfile` /
  `docker/service.Dockerfile` へ置換
- `.github/workflows/ci.yml`（`check-backend` / `test-backend`）— メンバー単位に分割
- `CLAUDE.md` — モノレポ構成・バックエンド節を更新

### 参考実装（`app_ref/services/`、踏襲元）

- `app_ref/services/pyproject.toml` — `[tool.uv.workspace] members`・ruff 集約
- `app_ref/services/api/pyproject.toml` — `[tool.uv.sources] respec-shared = { workspace = true }`
- `app_ref/services/worker/pyproject.toml` — worker（= service 相当）の依存・extra 構成
- `app_ref/services/shared/pyproject.toml` — hatchling `packages = ["shared"]`
- `app_ref/services/shared/shared/enums.py` — `JobType` / `JobStatus` の `StrEnum`（shared/enums.py の元）
- `app_ref/services/shared/shared/blob.py` / `schemas/base.py` — Blob 参照・共有基底スキーマ
- `app_ref/services/api/Dockerfile` / `worker/Dockerfile`（+ `*.Dockerfile.dev`）— マルチステージ
  uv workspace ビルド（`uv sync --package ...`）
- `app_ref/services/worker/worker/main.py` / `registry.py` — `$requestRef` 解決・パイプライン登録
  （service の `pipelines/` 設計の参考。実装は 018）
- `app_ref/docker-compose.yml` / `docker-compose.dev.yml` — api + worker の `develop.watch` 構成

### 関連 Issue（相互参照）

- **本 issue（015）** `docs/issue/015-backend-api-service-split-monorepo.md` — 基盤（依存なし）
- **016** `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks +
  GCS スピルオーバー + Job ライフサイクル（service が Cloud SQL に結果を直書き）（依存: 015）
- **017** `docs/issue/017-terraform-gcp-infrastructure.md` — GCP 版 Terraform（依存: 015, 016）
- **018** `docs/issue/018-stack-analysis-async-job-on-service.md` — ADK スタック解析を service へ
  移し非同期ジョブ化（依存: 015, 016）

### 規約（CLAUDE.md）

- バックエンド: Python 3.13 / `uv` 管理 / 4 スペース・ダブルクォート・120 字 / ruff + ty
- **Annotated DI param 順序を変えない**（`DeadlockDetectedError` 回避）
- シークレットは Secret Manager（プレーンテキスト環境変数禁止）
- レート制限はエッジ（Cloud Armor）で強制 — 本番の api 前段で `compose.prod.yml` の Traefik
  ルールと等価な設定を持つ
- DB は Cloud SQL (PostgreSQL 17, pgvector)。ローカルは `pgvector/pgvector:pg17`
- コンテナレジストリ = Artifact Registry、CI/CD 認証 = Workload Identity Federation
