# 返済 PR 生成パイプラインを service に追加する（Gemini リファクタ案 + GitHub 書込）

## 概要

Matrix 負債レジストリの負債詳細には「返済 PR を作成」アクションがあるが
（`frontend/src/lib/components/matrix/debt-actions.svelte:28` の `createRepaymentPr` ボタン）、
その実体は `frontend/src/lib/api/client.ts:331` で `ComingSoonError` を throw するスタブである。
本 issue は、対象の **コード負債（`code_debts`、Issue 028）に対して自動リファクタ案を生成し、
GitHub に返済 PR を作成して `code_debts.related_pr` / `status=in_pr` を更新する** service 非同期
パイプラインを、Issue 018 の `stack_analysis` を雛形に新設する。

具体的には、(1) `JobType` に `repayment_pr_generation` を追加し、(2) `shared/shared/schemas` に
request/result（`StackAnalysisRequest` / `StackAnalysisResult` と同じ `JobRequestBase` /
`JobResultBase` 継承・`GitHubRef` 方式 B）を定義、(3) `service/service/pipelines/repayment_pr_generation.py`
の `process(request, ctx)` で **対象 `code_debt` のコード文脈を取得 → Gemini（Vertex AI + ADC）で
リファクタ案（差分）を生成 → `GitHubGitClient`（書込拡張）/ `GitHubAppService`（方式 B）で
ブランチ作成 + ファイル更新 + PR 作成 → `code_debts.related_pr`（PR 番号/URL）と `status=in_pr` を
`ctx.session` で更新**し、(4) `service/service/registry.py` に三つ組登録、(5) api は
`POST .../debts/{debt_id}/repayment-pr` → `202 {job_id}` の enqueue に徹する。

> 本 issue は **返済 PR の生成と `code_debts` 行のステータス更新まで**。負債検知（`code_debts` の生成）は
> Issue 028、知識負債は Issue 030、配信一覧/詳細・dismiss/assign の PATCH は Issue 031 が担当する。
> 本 issue は **GitHub 書込権限を伴う唯一のパイプライン**であり、認可（`OrgAdminScope`）・監査・方式 B での
> token mint を特に厳守する。フロントの `createRepaymentPr`（`client.ts:331` のスタブ）の実 API 差し替えを含む。

## 背景・目的

### 現状（フロントだけ・裏側ゼロ）

- `frontend/src/lib/api/schemas.ts:230-249` の `codeDebtSchema` は `status`（`open` / `in_pr` /
  `resolved` / `dismissed`、`:237`）と `related_pr`（`str | null`、`:239`）を契約として持つ。
  返済 PR が作成されると `status` が `in_pr` へ、`related_pr` に PR 参照（mock では `"#4012"`、
  `frontend/src/lib/api/mock/debts.ts:79,81`）が入る、という遷移が UI 上で表現されている。
- `frontend/src/lib/api/client.ts:331` の `createRepaymentPr(orgSlug, debtId)` は `ComingSoonError` を
  throw するスタブで、`debt-actions.svelte:28` のボタンは「準備中」トースト
  （`debt-actions.svelte:17`）を出すだけである。`dismissDebt`（`client.ts:336`）/
  `assignDebt`（`:341`）も同様のスタブだが、これらは **Issue 031** の PATCH で差し替える（本 issue 対象外）。
- Agents ナラティブの自律ループにも返済ステージが描かれている：`frontend/src/lib/mocks/agent-activity.ts:142`
  の pipeline ステージ `key:"repay"` に「返済 PR 作成」ノード（`status:"failed"`, `retryable:true`）が
  あり、`:112` の `pr_review` evidence は `/matrix/debt-002` へクロスリンクする。返済 PR 生成は
  Code Debt Agent の `repay` ステージの実体である（自律ループの統合は **Issue 036**）。
- バックエンドには返済 PR 生成パイプラインも GitHub 書込経路も存在しない。`GitHubGitClient`
  （`backend/service/service/services/github_git_client.py:61`）は `list_repositories` /
  `get_repository_tree` / `get_file_content` 等の **読み取り REST のみ**で、ブランチ作成・コミット・
  PR 作成の書込メソッドを持たない。

### 目的

1. 対象 `code_debt` の **コード文脈（該当ファイル・`code_snippet`・`archaeology_notes`）を Gemini に渡し、
   リファクタ案（修正後ファイル内容または差分）を生成**する service パイプラインを新設する。
2. 生成した修正を **GitHub に返済 PR として作成**する（ブランチ作成 → ファイル更新 → PR open）。
   `GitHubGitClient` に書込メソッドを追加し、方式 B（`installation_id` のみ payload 搬送、service が
   Secret Manager から token mint）を厳守する。
3. PR 作成後、service が `ctx.session` で対象 `code_debts` 行の `related_pr`（PR 番号/URL）と
   `status=in_pr` を更新する（`shared.worker.run_task` の冪等な Job ライフサイクルに乗せる、Issue 018 同型）。
4. api は `POST .../debts/{debt_id}/repayment-pr` で **enqueue + `202 {job_id}` 返却**に徹し、進捗は既存
   `GET /api/v1/jobs/{id}`（`backend/api/app/api/v1/jobs.py`）でポーリングする。
5. フロントの `createRepaymentPr`（`client.ts:331`）を実 API へ差し替え、`debt-actions.svelte` の
   ボタンを enqueue → ポーリング → PR リンク表示の導線にする。

### 前提 issue（depends_on）

- **Issue 028** `docs/issue/028-backend-code-debt-detection-pipeline.md` — `code_debts` ORM
  （`type` / `severity` / `status[open/in_pr/resolved/dismissed]` / `related_pr` / `related_adr` /
  `archaeology_notes` / `code_snippet` / `file_path` / `repo` / `code_debt_score` 等）と検知パイプライン。
  本 issue は **`code_debts` 行を入力**とし、その `file_path` / `code_snippet` / `archaeology_notes` を
  リファクタ案生成の文脈に使い、`related_pr` / `status` を更新する。`code_debts` テーブルが前提。
- **Issue 031** `docs/issue/031-backend-overview-and-debt-registry-api.md` — 負債レジストリの配信
  （`GET .../debts` / `GET .../debts/{debt_id}`）と PATCH（dismiss/assign）。本 issue の
  `POST .../debts/{debt_id}/repayment-pr` は **031 が確定する `/orgs/{slug}/projects/{project_slug}/debts/{debt_id}`
  ルート形・`debt_id` の解決・`OrgScope` 認可基盤の隣に置く**（031 のルーターに追加するか、専用ルーターを
  足すかは実装判断）。031 が `createRepaymentPr` を「033 で差し替え」と明記している（031 タスク欄）。

> 028 の `code_debts` カラム名・`status` enum と、031 のルート形（`debt_id` パスパラメータ・`OrgScope`）が
> 確定するまで、本 issue の `code_debts` 更新カラム・ルートプレフィックスは仮であり、両 issue の最終形に
> 合わせて整合させる（捏造しない）。

## データモデル（新規/変更テーブル）

**本 issue は新規テーブルを作らない。** 変更は **既存 `code_debts`（Issue 028 所有）への行更新のみ**で、
スキーマ変更（カラム追加）は伴わない。返済 PR 作成時に service が以下を更新する：

| テーブル | 変更 | 内容 |
|---|---|---|
| `code_debts`（028） | 行 UPDATE のみ | `related_pr`（`str`、PR 番号 `"#4012"` または URL）/ `status`（`open` → `in_pr`） |

- `related_pr` の格納形式（`"#<number>"` か フル URL か）は `codeDebtSchema.related_pr`（`schemas.ts:239`、
  `str | null`）と mock（`debts.ts:81` は `"#4012"`）に合わせ、**PR 番号文字列 `"#<number>"`** を基本とする
  （PR URL を別カラムにするかは 028 のスキーマと整合させる。捏造せず最小に留める）。
- Alembic マイグレーションは **不要**（既存カラムの更新のみ）。`code_debts.related_pr` / `status` カラムが
  028 のマイグレーション（`0006` 想定）で既に存在することを前提とする。

> 監査用に「どの Job がどの PR を作ったか」を残す必要があれば、`Job.result_data`（後述の
> `RepaymentPrGenerationResult`）に `debt_id` / `pr_number` / `pr_url` / `branch` を書く形で足りる
> （`GET /jobs/{id}` で追跡可能）。専用の監査テーブルを足すかは「対象外・保留」に記す。

## API（`/api/v1/...`）

api は **enqueue + `202` + ポーリング**に徹する（`stack.py:105-143` の `analyze_stack` を雛形）。
返済 PR の生成・GitHub 書込は service が担う。

### `POST .../debts/{debt_id}/repayment-pr` → `202`

- ルートは Issue 031 が確定する負債レジストリのプレフィックス
  `/orgs/{slug}/projects/{project_slug}/debts/{debt_id}/repayment-pr` に揃える
  （031 のルーター `backend/api/app/api/v1/debts.py`（または `overview.py`）に追加する）。
- `stack.py::analyze_stack`（`backend/api/app/api/v1/stack.py:105-143`）と同型の enqueue：
  1. `OrgAdminScope`（`backend/api/app/api/deps.py:65`）で **書込権限を持つ org 管理者**に限定する
     （閲覧系の `OrgScope`（`deps.py:64`）より厳しい。GitHub 書込を伴うため）。
  2. `debt_id` から `code_debts` 行を読み、対象 project の repo（`owner` / `repo`）・`file_path` /
     `code_snippet` / `archaeology_notes` を取得する。存在しなければ 404（`NotFoundError`、
     `backend/api/app/core/exceptions.py`）。既に `status=in_pr`（PR 作成済み）なら 409 / 既存
     `related_pr` を返す設計判断（重複 PR を避ける、後述の冪等性）。
  3. installation_id を解決し（`InstallationIdDep`、`backend/api/app/api/v1/github.py:133`）、方式 B
     （`installation_id` のみ payload）で
     `enqueue_job(session, dispatcher, blob_client, job_type=JobType.REPAYMENT_PR_GENERATION,
     payload=..., created_by=current_user.id)`（`backend/api/app/services/job_orchestrator.py:29`）を呼ぶ。
     payload には `debt_id` / `owner` / `repo` / `branch`（PR のベース）/ `requested_by`（監査用）/
     `github.installation_id` を載せる。
  4. レスポンスは既存 `JobEnqueuedOut`（`backend/api/app/schemas/job.py`、`{job_id, status}`）を流用。
     フロントは `analyzeStackJobSchema`（`schemas.ts:157`）と同形で受ける。
- 進捗・完了は既存 `GET /api/v1/jobs/{id}`（`backend/api/app/api/v1/jobs.py:57`）でポーリング。
  `Job.result_data` に PR 番号/URL・ブランチ名・trace が入る（`jobs.py:72-77` の `STACK_ANALYSIS`
  分岐に倣い、`REPAYMENT_PR_GENERATION` 用の持ち上げを足すかは実装判断。最小は汎用 `result_data` 配信）。

> **認可は `OrgScope` ではなく `OrgAdminScope`。** 返済 PR 作成は GitHub リポジトリへの書込（ブランチ作成・
> PR open）を伴う破壊的アクションのため、閲覧系の負債配信（Issue 031 の `GET .../debts` は `OrgScope`）より
> 強い権限を要求する。**Annotated DI param 順序を変更しない**（CLAUDE.md「`Annotated[T, Depends(f)]` deps の
> 宣言順序を変えない」。`projects.py:127` の PATCH 引数並びに倣う）。

## パイプライン・非同期

### `JobType` 追加（`backend/shared/shared/enums.py:11-16`）

`JobType` に `REPAYMENT_PR_GENERATION = "repayment_pr_generation"` を追加（`STACK_ANALYSIS` の隣、
`enums.py:16`）。lowercase snake_case = queue path `repayment-pr-generation`（`enums.py:5` の規約）。

### request / result スキーマ（`backend/shared/shared/schemas/repayment_pr_generation.py`）

`stack_analysis.py`（`backend/shared/shared/schemas/stack_analysis.py:58-77`）を雛形に：

- `RepaymentPrGenerationRequest(JobRequestBase)`: `debt_id: str` / `owner: str` / `repo: str` /
  `branch: str = "main"`（PR のベースブランチ）/ `github: GitHubRef`（`installation_id` のみ＝方式 B、
  `stack_analysis.py:45-55` の `GitHubRef` を再利用）/ `requested_by: str`（監査用）。
- `RepaymentPrGenerationResult(JobResultBase)`: `debt_id: str` / `pr_number: int | None` /
  `pr_url: str | None` / `branch: str | None`（作成した head ブランチ名）/ `trace: list[str]`
  （生成・PR 作成ステップ）。`Job.result_data` に書かれ（camelCase, `by_alias=True`、
  `stack_analysis.py` ヘッダ参照）、`GET /jobs/{id}` で読まれる。

### registry 三つ組登録（`backend/service/service/registry.py:15-18`）

`PIPELINES` に `JobType.REPAYMENT_PR_GENERATION.value: (RepaymentPrGenerationRequest,
RepaymentPrGenerationResult, repayment_pr_generation.process)` を追加（`stack_analysis` の隣）。
重い依存（Gemini/Vertex/GitHub 書込）は service のみに置き shared/api に漏らさない（`registry.py:1-8` の方針）。

### `process(request, ctx)`（`backend/service/service/pipelines/repayment_pr_generation.py`）

`stack_analysis.py::process`（`backend/service/service/pipelines/stack_analysis.py:361-389`）を雛形に：

1. `ctx.session` が `None` なら `RuntimeError`（`stack_analysis.py:368`）。
2. **冪等性（Cloud Tasks は at-least-once）:** `ctx.session` で `code_debts(debt_id)` を読み、既に
   `status=in_pr` かつ `related_pr` が埋まっていれば **PR を再作成せずスキップ**して既存 PR 参照を結果に返す
   （`shared.worker.run_task` の Job 冪等性に加え、GitHub 副作用の二重実行を防ぐ）。
3. 方式 B でトークン mint（`stack_analysis.py:332-342` の `_mint_installation_token` と
   `service.services.github_app.GitHubAppService.get_installation_token`
   `backend/service/service/services/github_app.py:49` を流用）。
4. `GitHubGitClient`（書込拡張版）で対象ファイル内容を取得（`get_file_content`、
   `github_git_client.py`）。`code_debt.code_snippet` / `archaeology_notes` と併せて Gemini に渡す文脈を組む。
5. **リファクタ案生成**: `gemini_stack_service`（Vertex AI + ADC、`stack_analysis.py:27` /
   `_vertex_model_name` `stack_analysis.py:44-57` = `projects/` で始まる model 名で ADK が Vertex+ADC を
   自動選択）で **修正後ファイル内容（または差分）と PR タイトル/本文**を生成する
   （`response_mime_type=application/json` で構造化、`gemini_stack_service` の方式を踏襲）。
6. **GitHub 書込（PR 作成）**: `GitHubGitClient` に追加する書込メソッドで
   (a) ベースブランチの最新 SHA から head ブランチ作成 → (b) 該当ファイルを修正内容で更新（commit）→
   (c) PR を open（タイトル/本文に `archaeology_notes` と「自動生成」の注記を含める）。
7. PR 作成後、`ctx.session` で `code_debts(debt_id)` を `related_pr="#<pr_number>"` /
   `status="in_pr"` に UPDATE する（`stack_analysis.py:213-233` の upsert 同様に同一セッションで DML）。
8. `RepaymentPrGenerationResult`（`pr_number` / `pr_url` / `branch` / `trace`）を返す
   （`shared.worker.run_task` が `Job.result_data` へ冪等に書く）。

> **`GitHubGitClient` の書込拡張が本 issue 最大の新規実装点。** 現クライアント
> （`github_git_client.py:61-`）は読み取り REST のみで、`create_branch` / `create_or_update_file` /
> `create_pull_request` 相当を新設する必要がある。GitHub App installation token に **`contents:write` /
> `pull_requests:write` スコープ**が付与されている前提を本 issue で明示し、足りない場合は GitHub App の
> 権限設定（インストール権限の再同意）が前提作業になる旨を注記する。

### 定期スキャン

返済 PR 生成は **ユーザ起点のアクション**（負債詳細の「返済 PR を作成」押下）であり、定期実行の対象では
ない。CLAUDE.md の Cloud Functions/Pub-Sub 定期スキャンは検知系（Issue 028/030、巡回 enqueue は Issue 037）
の責務で、本 issue は手動トリガ（`POST .../debts/{debt_id}/repayment-pr`）のみ。

## タスク

### shared（`backend/shared/shared/`）

- [ ] `enums.py:16`（`STACK_ANALYSIS` の隣）に `REPAYMENT_PR_GENERATION = "repayment_pr_generation"` を追加。
- [ ] `schemas/repayment_pr_generation.py` を新設（`stack_analysis.py:58-77` 雛形。
      `RepaymentPrGenerationRequest` / `RepaymentPrGenerationResult`、`GitHubRef`（`stack_analysis.py:45-55`）
      再利用・`JobRequestBase`/`JobResultBase`（`schemas/job.py:12,20`）継承）。
- [ ] 新規 ORM は無し（`code_debts` は Issue 028 所有・行更新のみ）。`models/__init__.py` の変更は不要。

### api（`backend/api/app/`）

- [ ] `POST .../debts/{debt_id}/repayment-pr` を Issue 031 の負債ルーター
      （`backend/api/app/api/v1/debts.py`）に追加（`stack.py:105-143` の `analyze_stack` をコピーし
      `job_type=JobType.REPAYMENT_PR_GENERATION` に変更）。`OrgAdminScope`（`deps.py:65`）+
      `InstallationIdDep`（`github.py:133`）+ `JobEnqueuedOut`（`schemas/job.py`）流用、
      Annotated DI param 順序厳守（`projects.py:127` の並びに倣う）。
- [ ] `debt_id` から `code_debts` 行を読んで `owner`/`repo`/`file_path` を payload に積む処理を足す
      （404 / 既 `in_pr` 時の 409 ハンドリングは設計判断）。
- [ ] Alembic マイグレーションは **追加しない**（既存 `code_debts` の行更新のみ。028 の `0006` 前提）。
- [ ] `GET /api/v1/jobs/{id}`（`jobs.py:57`）が返済 PR ジョブの `result_data`（PR 番号/URL）を返せること
      （`jobs.py:72` の `STACK_ANALYSIS` 分岐に倣い `REPAYMENT_PR_GENERATION` の持ち上げを足すかは実装判断。
      最小は汎用 `result_data` 配信で可）。

### service（`backend/service/service/`）

- [ ] `pipelines/repayment_pr_generation.py` の `process(request, ctx)` を新設（`stack_analysis.py:361-389`
      雛形。方式 B トークン mint `stack_analysis.py:332-342`、`ctx.session` で `code_debts` 行更新
      `stack_analysis.py:213-233` 同様、冪等チェック）。
- [ ] `services/github_git_client.py`（`:61`）に **書込メソッド**を追加（`create_branch` /
      `create_or_update_file` / `create_pull_request` 相当の REST 呼び出し）。token は方式 B で mint
      （`github_app.py:49` `get_installation_token`）。`contents:write` / `pull_requests:write` スコープ前提。
- [ ] Gemini でリファクタ案（修正内容 + PR タイトル/本文）を生成（`gemini_stack_service`
      `stack_analysis.py:27` / `_vertex_model_name` `stack_analysis.py:44-57` 流用、
      `response_mime_type=application/json`）。
- [ ] `registry.py:15-18` の `PIPELINES` に三つ組登録（`JobType.REPAYMENT_PR_GENERATION.value`）。

### frontend（`frontend/src/`）

- [ ] `client.ts:331` の `createRepaymentPr(orgSlug, debtId)` スタブ（`ComingSoonError` throw）を
      **実 API へ差し替え**：`POST .../orgs/${orgSlug}/projects/${projectSlug}/debts/${debtId}/repayment-pr`
      を叩き `202 {job_id}` を返す（`analyzeStack` `client.ts:257` と同型）。`getJob`（`client.ts:265`）で
      ポーリングし、完了時に PR リンクを表示する。`schemas.ts` の `analyzeStackJobSchema`（`:157`）/
      `jobStatusSchema`（`:163`）を流用（PR 用に `result_data` の PR 番号/URL を読む形を追加するかは設計判断）。
- [ ] `client.ts:331` の引数を project スコープ化（`orgSlug` のみ → `projectSlug` 追加。031 の
      `listDebts`/`getDebt` の project スコープ化と整合）。
- [ ] `debt-actions.svelte:28` の「返済 PR を作成」ボタンを enqueue → ポーリング → PR リンク表示の導線に改修
      （`Hourglass` アイコン・`debt_action_soon_suffix`（`debt-actions.svelte:32`）の「準備中」表示を解消）。
      `dismissDebt`（`client.ts:336`）/ `assignDebt`（`:341`）は **本 issue では据え置き**（Issue 031）。

### infra

- [ ] 追加インフラなし（既存 service Cloud Run / Cloud Tasks で実行）。**service runtime SA の前提を確認**：
      Vertex AI（`roles/aiplatform.user`）+ Secret Manager（`GITHUB_APP_PRIVATE_KEY` 参照）は Issue 017/018 で
      付与済み。GitHub App 側の installation 権限に `contents:write` / `pull_requests:write` が含まれることを確認
      （足りなければ GitHub App 権限の再設定が前提作業。本 issue 内に注記）。

### test

- [ ] api（`backend/api/tests/`）: `POST .../debts/{debt_id}/repayment-pr` が `202` + `job_id` を返し、
      `Job(QUEUED, type=repayment_pr_generation)` が作成され、`MockTaskDispatcher.dispatch` が 1 回
      呼ばれること（018 のテスト方針に倣う）。`OrgScope` のみのメンバー（非 admin）が 403、不在 `debt_id` が 404、
      既 `in_pr` が 409（設計判断どおり）になること。
- [ ] service（`backend/service/tests/`）: `repayment_pr_generation.process` のパイプラインテスト
      （`GitHubGitClient` 書込メソッドと Gemini/Vertex を **モック**）。PR 作成後に `code_debts` 行が
      `status=in_pr` / `related_pr` 更新されること、再配送（at-least-once）で **PR が二重作成されない**
      冪等性（既 `in_pr` ならスキップ）、方式 B トークン mint 経路のテスト。

## 完了条件

- 負債詳細の「返済 PR を作成」押下で api が `202` + `job_id` を返し、api リクエストは PR 作成完了を待たずに
  即返る（生成・GitHub 書込は service で実行）。
- service が api リクエスト外で Gemini リファクタ案生成 + GitHub 書込（ブランチ作成・ファイル更新・PR open）を
  実行し、`code_debts` 行の `status=in_pr` / `related_pr` を Cloud SQL に永続化する（`Job` 行も
  `shared.worker.run_task` 経由で `COMPLETED`/`FAILED` に直接更新、api コールバック・Pub/Sub 無し）。
- 同一 Job の再配送で **PR が二重作成されない**（既 `in_pr` ならスキップ）。
- `GET /api/v1/jobs/{id}` で返済 PR ジョブの `status` と PR 番号/URL がポーリングできる。
- 認可が `OrgAdminScope` 下にあり（GitHub 書込のため `OrgScope` より強い）、方式 B で GitHub token が
  service 内 mint され **キュー/GCS に平文の秘密が残らない**。
- フロントの `createRepaymentPr`（`client.ts:331`）が実 API を叩き、`ComingSoonError` スタブが解消され、
  完了後に PR リンクが表示される。
- バックエンド: `cd backend && uv run ruff check shared/shared api/app service/service &&
  uv run ruff format --check ...` / `uv run ty check ...` / `uv run --directory <member> pytest` が通る。
- フロント: `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語, Keep a Changelog）に `Added`（返済 PR 生成パイプライン /
  `repayment_pr_generation` JobType / `POST .../debts/{debt_id}/repayment-pr`）と `Changed`
  （`createRepaymentPr` を実 API へ）の追記。

## 対象外・保留

- **負債検知**（`code_debts` の生成）— Issue 028 / 知識負債は Issue 030。本 issue は既存 `code_debts` 行を入力にする。
- **配信一覧/詳細・dismiss/assign**（`GET .../debts` / `GET .../debts/{id}` / `PATCH .../debts/{id}` =
  `dismissDebt`/`assignDebt`）— Issue 031。本 issue が触る `code_debts` 更新は `related_pr` / `status` のみ。
- **知識負債の返済**（`knowledgeDebtSchema` は `related_pr` を持たない、`schemas.ts:251-268`）— 対象外。
  返済 PR は **コード負債（`code_debts`）のみ**を対象とする（`assigned_agent:"code_debt"`、`schemas.ts:247`）。
- **PR マージ後の `status=resolved` への遷移** — 本 issue は `in_pr` までを担う。`resolved` は PR マージ検知
  （Webhook / 定期スキャン）が必要で将来課題（Issue 037 の延長 / 別 issue）。
- **Agents 自律ループ（`repay` ステージ）への統合**（`agent-activity.ts:142` の「返済 PR 作成」ノード・
  `retry` 導線）— Issue 036。本 issue は単発の返済 PR 生成パイプラインを提供し、036 が `repay` ステージとして
  sub-enqueue / 直接呼び出しで束ねる。
- **生成コードの品質保証**（CI 自己検証・再生成ループ）— Gemini 出力は非決定的。本 issue は PR を open する
  までで、レビュー/マージは人間が行う前提（生成 PR である旨を PR 本文に明記）。`verify` ステージは Issue 036。
- **監査専用テーブル**（誰がどの PR を作ったか）— `Job`（`created_by` / `result_data`）で追跡可能なため
  本 issue では新設しない。要件化されれば別途。

## 参考

- 関連 issue
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 202 enqueue / `GET /jobs/{id}` / 方式 B /
    `(Request, Result, process)` 三つ組の雛形（様式・パターンの正）
  - `docs/issue/028-backend-code-debt-detection-pipeline.md` — `code_debts` ORM・`status`/`related_pr`（前提・入力元）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — 負債レジストリ配信・PATCH・ルート形（前提・ルーター隣接）
  - `docs/issue/008-matrix-debt-registry-drilldown.md` — `codeDebtSchema` の製品セマンティクス（`status`/`related_pr`）
  - `docs/issue/036-backend-agents-autonomous-loop-and-narrative.md` — `repay` ステージへの統合（後続）
  - `docs/issue/037-backend-periodic-scan-cloud-functions.md` — PR マージ検知・定期化（後続）
- フロント契約・mock（裏取り済み file:line）
  - `frontend/src/lib/api/schemas.ts:230-249` — `codeDebtSchema`（`status` `:237` / `related_pr` `:239` /
    `assigned_agent:"code_debt"` `:247`）、`:157` `analyzeStackJobSchema` / `:163` `jobStatusSchema`
  - `frontend/src/lib/api/client.ts:331` — `createRepaymentPr`（`ComingSoonError` スタブ＝差し替え対象）、
    `:257` `analyzeStack` / `:265` `getJob`（enqueue+ポーリング同型）、`:336`/`:341` `dismissDebt`/`assignDebt`（031）
  - `frontend/src/lib/components/matrix/debt-actions.svelte:28` — 「返済 PR を作成」ボタン（導線改修対象）
  - `frontend/src/lib/api/mock/debts.ts:79-81` — `status:"in_pr"` / `related_pr:"#4012"`（PR 作成後の目標形）
  - `frontend/src/lib/mocks/agent-activity.ts:142,166` — `repay` ステージ「返済 PR 作成」ノード（036 で統合）
- 既存 backend（雛形・流用）
  - `backend/service/service/pipelines/stack_analysis.py:361-389`（`process`）/ `:332-342`（方式 B mint）/
    `:213-233`（`ctx.session` DML）/ `:27,44-57`（Gemini Vertex+ADC）
  - `backend/service/service/registry.py:15-18`（三つ組登録）
  - `backend/service/service/services/github_app.py:49`（`get_installation_token`）/
    `github_git_client.py:61`（読み取りのみ＝書込メソッド追加対象）/ `gemini_stack_service.py`（Vertex AI + ADC）
  - `backend/shared/shared/schemas/stack_analysis.py:45-77`（`GitHubRef` / request/result 雛形）/
    `schemas/job.py:12,20`（`JobRequestBase`/`JobResultBase`）
  - `backend/shared/shared/enums.py:11-16`（`JobType` 追加点）
  - `backend/api/app/api/v1/stack.py:105-143`（enqueue 202 雛形）/ `api/v1/jobs.py:57-77`（ポーリング・
    `result_data` 持ち上げ）/ `api/v1/github.py:133`（`InstallationIdDep`）/ `api/v1/router.py:8-20`（ルーター登録）
  - `backend/api/app/api/deps.py:64,65`（`OrgScope` / `OrgAdminScope`）/ `services/job_orchestrator.py:29`
    （`enqueue_job`）/ `api/v1/projects.py:42,115,127`（project スコープルート形・PATCH 引数並び）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — Vertex AI + ADC（API キー不使用）・Secret Manager 必須・方式 B・
    GitHub 書込は `OrgAdminScope`・Annotated DI param 順序厳守・`JobType` 追加・`registry.py` 三つ組登録・
    snake_case 配信・更新は PATCH・ゲート（`uv run ruff`/`ty`/`pytest`、`bun run check`/`lint`/`test:unit`）・
    `CHANGELOG.md`（日本語）
