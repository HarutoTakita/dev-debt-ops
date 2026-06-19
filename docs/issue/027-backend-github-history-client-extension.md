# GitHubGitClient に commit 履歴・blame・依存抽出取得を追加し方式 B を維持する

## 概要

現在の `GitHubGitClient`（`backend/service/service/services/github_git_client.py`）は GitHub REST の
ツリー/内容取得しか持たない — `list_repositories` / `get_repository` / `list_branches` /
`get_repository_tree`（`git/trees/{branch}?recursive=1`）/ `get_file_content`（`contents/{path}`）の 5 メソッドだけで、
**commit 履歴・blame・PR レビューメタを取得する経路が一切無い**（`github_git_client.py:76-185`）。

しかし後続の解析パイプライン（028 コード負債 / 029 KC 算出 / 030 知識負債）は、
- 「誰がそのファイルを書いたか（authorship）」「最後に触ったのはいつか」「著者は離脱したか」
- 「その変更は PR でレビューされたか / 自動 approve だったか」
- 「ファイル間の依存（import）はどうなっているか = ワームホール」

を必要とする。本 issue は **service 層に「git 履歴アクセス」「authorship 突合」「依存グラフ抽出」の 3 つの
共通ヘルパを新設**し、各解析パイプラインが共通利用できる土台を確定する。重い解析ロジック本体や
KC スコア式・配信 API は本 issue の責務ではない（後続 028/029/030/031 が所有）。

GitHub トークンの受け渡しは **issue 018 で確立した方式 B（`installation_id` のみキュー搬送、service が
Secret Manager の鍵から token を mint）を厳守**する（`stack_analysis._mint_installation_token`
`stack_analysis.py:332-342` / `GitHubAppService.get_installation_token` `github_app.py:49-71`）。

> 本 issue は新しい JobType / パイプライン / テーブルを **作らない**。`GitHubGitClient` の拡張・
> 新クライアント・突合ユーティリティ・依存抽出ヘルパという **service の道具立て** を整え、028 以降が
> `process(request, ctx)` の中から呼ぶだけで git 履歴・authorship・依存を得られる状態にすることが主眼である。
> 取得方式（REST 拡張 vs git clone）の選定と File 同一性・dev 識別子の正規化は **ADR 化** する。

## 背景・目的

### 現状（履歴アクセスが無い）

`GitHubGitClient`（`github_git_client.py:61-189`）は installation access token を `Authorization: Bearer`
に載せた `httpx.AsyncClient` で REST を叩くが、提供するのはツリー/内容のみ：

- `get_repository_tree`（`github_git_client.py:146`）— `git/trees/{branch}?recursive=1` から `blob`/`tree` を返す。
- `get_file_content`（`github_git_client.py:164`）— `contents/{path}?ref=...` を base64 デコードして返す。

`commits` / `blame`（GraphQL）/ `pulls`（PR・レビュー）に触れるメソッドが無いため、KC(file,dev) の前提である
**authorship・最終更新・レビュー有無** を得る術が service に存在しない（foundation マップ「最大の技術リスク」）。

### 方式選定（REST 拡張 vs ローカル git clone）— ADR 必須

| 方式 | 取得手段 | 長所 | 短所 |
|---|---|---|---|
| **方式 1: REST/GraphQL 拡張**（推奨・MVP） | 既存 `GitHubGitClient` に `list_commits` / `get_blame`（GraphQL）/ `list_pull_requests`+レビュー を追加 | 既存 token 認証・コンテナ無依存・小規模で十分 | 大規模リポジトリで REST レート制限（installation token は時間あたり上限あり）に当たりやすい |
| **方式 2: git clone**（フル・将来） | installation token を埋めた URL で shallow clone し、ローカル `git log` / `git blame` を実行 | レート制限を回避・blame が高速 | service コンテナのディスク/権限コスト、private ソースの一時残留リスク、clone への installation token 利用可否の検証要 |

- [ ] **どちらを採るか / 段階移行の閾値（リポジトリ規模・レート余裕）を ADR に記す**
      （`docs/adr/` に新規。MVP は方式 1、大規模で方式 2 へ切替の線引き）。
      方式 2 を採る場合でも token は方式 B（service が mint）で、clone 一時データは処理後に必ず破棄する。

### 目的

1. `GitHubGitClient` を拡張（または新クライアント追加）し、**commit 履歴 / blame / PR レビューメタ** を取得できるようにする。
2. **authorship 突合ユーティリティ**（GitHub author の email/login ↔ `users.id`）を service に新設する。
3. **依存グラフ抽出ヘルパ**（import 解析）を新設し、`dependency`（`from_path` / `to_path` = ワームホール）の生成器を用意する。
4. 取得方式（REST 拡張 / clone）と File 同一性・dev 識別子の正規化を **ADR 化** する。
5. すべて **方式 B（installation_id のみ搬送、service が Secret Manager から mint）** を厳守する。

### 前提 issue（depends_on）

- **Issue 026** `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` —
  解析共有テーブル（`analysis_run` / `repo_file`）+ `dependency` ORM の前提・`JobType` 命名規約・
  File 同一性／dev 識別子の正規化方針（ADR）。本 issue の依存抽出ヘルパは 026 が定める `dependency`
  （`run_id` / `from_path` / `to_path`）の **生成器** を供給し、テーブル定義そのものは 026 が所有する。

> 本 issue は 018 で確立した方式 B・`PipelineContext`・`GitHubGitClient` 拡張点を前提とし、
> 026 が確定する共有テーブル（`repo_file` = File 同一性アンカー、`dependency` = ワームホール）に
> 値を流し込む「道具」を service に揃える。テーブル所有は 026、利用は 028/029/030 にある。

## データモデル（本 issue では新規テーブルを作らない）

本 issue は **service の道具立て**であり、ORM テーブル・Alembic マイグレーションは原則 **追加しない**。

- `dependency`（`run_id` / `from_path` / `to_path`）の **ORM 定義・Alembic は 026 が所有**。本 issue は
  その行を生成する純粋関数（依存抽出ヘルパ）を service に置くのみ。
- authorship 突合は **既存テーブルで完結**する想定：GitHub login は `oauth_account`（`backend/api/app/...`、
  `resolve_installation_id` が `OAuthAccount.access_token` で `/user` を叩き `login` を解決する経路 `github.py:88-101`）
  と `users.id` の対応で突合する。本 issue では新テーブルを足さず、突合は service 内ユーティリティ（純粋ロジック）として提供する。
  - 永続的な author↔user マッピングテーブルが必要だと判明した場合は ADR にその必要性を記し、
    **テーブル新設は 029（KC が dev_id を実際に使う issue）へ委譲**する（本 issue で先取り作成しない）。

> 雛形参照（テーブルを足す場合の形）：`backend/shared/shared/models/tech_stack.py`（`uuid4` PK・`JSON` 列・
> `UniqueConstraint`・`DateTime(timezone=True)`）/ `backend/api/app/alembic/versions/0003_add_tech_stacks.py`・
> `0005_add_jobs.py`（api が Alembic 所有、次番は 026 が 0006 を使用済みのため 0007 以降）。

## API（本 issue では公開 API を追加しない）

本 issue は **service 層の内部ヘルパのみ**を対象とし、`/api/v1/...` の新規エンドポイントは追加しない。
取得した履歴・authorship・依存を **配信する API は後続が所有**する：

- KC / Galaxy の配信（`personalGalaxySchema` の `wormholes`〔`from`/`to`〕`schemas.ts:298-301` への投影）は
  **032** が `GET .../galaxy` で返す。
- 負債一覧/詳細（`assignedDeveloperSchema` `schemas.ts:224-228` の `github_handle` / `coverage` / `certified_via`）は
  **031** が `GET .../debts` で返す。

本 issue が供給するのは、それら配信 issue が読む **DB 行（029 の `file_kc` / `dependency` 等）を埋めるための
service 内の取得・突合・抽出ロジック**である（snake_case 配信の責務は配信 issue 側）。

## パイプライン・非同期（service ヘルパの新設）

本 issue は **新 JobType / 新パイプラインを登録しない**（`shared/shared/enums.py` の `JobType` は echo/ping/stack_analysis のまま、
`service/service/registry.py` の `PIPELINES` も変更しない）。代わりに 028/029/030 の `process` から import される
**共通モジュール群**を `backend/service/service/services/` に追加する。

### (1) GitHubGitClient の履歴拡張（`github_git_client.py`）

既存の `GitHubGitClient`（installation token で認証する `httpx.AsyncClient`、`github_git_client.py:61-74`）に
以下を追加する（戻り値は既存の `@dataclass`（`RepositoryInfo` / `TreeItem` / `FileContent`）に倣った
新規 dataclass で表現する）：

- `list_commits(owner, repo, *, path=None, sha=None, since=None, per_page, page)` —
  `GET /repos/{owner}/{repo}/commits`（`path` 指定でファイル単位履歴）。`CommitInfo`（sha / author_login /
  author_email / authored_at / message）を返す。ページングは `list_branches`（`github_git_client.py:118-144`）のループ規約に倣う。
- `get_blame(owner, repo, path, ref)` — **GraphQL**（`POST /graphql`、`object(expression).blame(path)`）で
  行レンジ × commit/author を取得（REST に blame が無いため）。`BlameRange`（start_line / end_line / commit_sha /
  author_login / author_email）を返す。
- `list_pull_requests(owner, repo, *, state, per_page, page)` / `get_pull_request_reviews(owner, repo, number)` —
  `GET /repos/{owner}/{repo}/pulls` と `.../pulls/{number}/reviews`。`PullRequestInfo`（number / merged_at /
  merged_by_login）+ レビュー有無・approve 者（自動 approve 判定用）。

> 方式 2（clone）を選ぶ場合は、上記と同じ dataclass を返す **別実装クラス**（例 `GitCloneHistoryClient`）を
> 新設し、呼び出し側は同じインターフェースで切替可能にする（ADR で確定）。

### (2) authorship 突合ユーティリティ（新規モジュール）

`backend/service/service/services/` に GitHub author（email/login）↔ `users.id` の突合関数を新設する：

- 入力 = commit/blame から得た author の `login` / `email`、出力 = 対応する `users.id`（不明なら `None` で
  GitHub handle のまま保持）。
- 突合は `oauth_account`（GitHub OAuth の `login`）と `users` の対応に基づく（`resolve_installation_id` が
  user → `github_login` を解決する経路 `github.py:88-101` を参照）。email 一致は補助とし、曖昧時は login 優先。
- 本ユーティリティは `ctx.session`（`PipelineContext.session` `context.py`）で `oauth_account` を引く純粋寄りロジックとして提供し、
  028/030 の「形式レビューのみ / 理解者」区別や 029 の KC(file,dev) が dev_id を埋める際に再利用する。

### (3) 依存グラフ抽出ヘルパ（新規モジュール）

`backend/service/service/services/` に import 解析ヘルパを新設する：

- 入力 = `get_file_content`（`github_git_client.py:164`）で取得したファイル内容 + パス（言語は拡張子から判定）。
- 言語別 parser（最小: Python `import`/`from`、TS/JS `import`/`require`）で import 文を抽出し、
  リポジトリ内パスへ解決して `(from_path, to_path)` のペア列（= ワームホール `schemas.ts:298-301`）を生成する。
- 解決不能な外部依存（npm/pypi パッケージ等）は除外し、**リポジトリ内ファイル間のエッジのみ**を返す。
- 026 が定義する `dependency`（`run_id` / `from_path` / `to_path`）行へそのまま投入できる形に揃える
  （DML は 029 が `ctx.session` で行い、本 issue は **生成器（純粋関数）** のみ提供）。

### 方式 B の踏襲（必須）

- すべての履歴取得は `_mint_installation_token`（`stack_analysis.py:332-342`）と同型で、
  `GitHubAppService.get_installation_token(installation_id)`（`github_app.py:49-71`）が
  `config.github_app_private_key()` から mint した token を用いる。**キュー/GCS に token を載せない。**
- GraphQL も同じ installation token を `Authorization: Bearer` で使用する（`API_BASE` は REST と別だが認証は共通）。

### 定期スキャン

本 issue はトリガを持たない。定期スキャン（Cloud Functions + Cloud Scheduler/Pub-Sub）は
**037** が新設し、各 project を巡回して 028/029/030 を enqueue する。本 issue のヘルパはそこから間接的に呼ばれる。

## タスク

### ADR（方式確定・正規化）

- [ ] `docs/adr/` に「git 履歴取得方式（REST/GraphQL 拡張 vs ローカル clone）」と「File 同一性・dev 識別子の
      正規化（authorship 突合）」の ADR を新設する（MVP=方式 1、大規模で方式 2 への閾値・clone 一時データ破棄方針を明記）。

### service: 履歴拡張（`backend/service/service/services/github_git_client.py`）

- [ ] `CommitInfo` / `BlameRange` / `PullRequestInfo` の dataclass を追加する
      （既存 `RepositoryInfo` `github_git_client.py:11-23` / `TreeItem` `:42-49` / `FileContent` `:51-58` に倣う）。
- [ ] `list_commits` を追加する（`GET /repos/{owner}/{repo}/commits`、`path` 単位履歴・ページングは
      `list_branches` `github_git_client.py:118-144` のループ規約に倣う）。
- [ ] `get_blame` を GraphQL（`POST /graphql`）で追加する（REST に blame が無いため。installation token 共通）。
- [ ] `list_pull_requests` / `get_pull_request_reviews` を追加する（PR の merge・レビュー有無・approve 者）。
- [ ] レート制限/429・二次レート制限の握り（`raise_for_status` + バックオフ）を既存 `get_*` 同様に整える。
- [ ] （方式 2 採用時）`GitCloneHistoryClient` を新設し、同 dataclass を返す切替可能実装にする。

### service: authorship 突合ユーティリティ（新規モジュール）

- [ ] `backend/service/service/services/` に authorship 突合関数を新設する
      （GitHub `login`/`email` → `users.id`。`oauth_account` と `users` の対応で突合、login 優先・email 補助）。
- [ ] `resolve_installation_id` の `github_login` 解決経路（`backend/api/app/api/v1/github.py:88-101`）を参照根拠とし、
      突合不能時は `None`（GitHub handle 保持）にフォールバックする。
- [ ] `ctx.session`（`backend/shared/shared/pipelines/context.py`）で `oauth_account` を引く形に揃える。

### service: 依存抽出ヘルパ（新規モジュール）

- [ ] `backend/service/service/services/` に import 解析ヘルパを新設する
      （`get_file_content` `github_git_client.py:164` の内容を入力に、言語別 parser で import を抽出）。
- [ ] リポジトリ内パスへ解決し `(from_path, to_path)` ペア列（ワームホール `frontend/src/lib/api/schemas.ts:298-301`）を返す。
- [ ] 出力を 026 の `dependency`（`run_id`/`from_path`/`to_path`）行へ投入できる構造体に揃える（DML は 029 が行う）。

### service: 方式 B の踏襲

- [ ] 履歴取得・GraphQL を `GitHubAppService.get_installation_token`（`backend/service/service/services/github_app.py:49-71`）
      で mint した token で行い、`_mint_installation_token`（`backend/service/service/pipelines/stack_analysis.py:332-342`）の
      パターンに合わせる（キュー/GCS に秘密を残さない）。

### frontend

- [ ] **本 issue ではフロント変更なし。** 本 issue は service 内部ヘルパのみで、`client.ts` の mock 差し替えは
      これらヘルパを消費する後続（031 の `getOverview`/`listDebts`/`getDebt`、032 の `getGalaxy`）が行う。

### infra

- [ ] **本 issue ではインフラ変更なし**（方式 1 の場合）。方式 2（clone）採用時のみ、service コンテナの
      一時ディスク要件を ADR に記し、必要なら 017/025 の Cloud Run 設定 follow-up として切り出す。

### テスト（`backend/service/tests/`）

- [ ] `list_commits` / `get_blame` / `list_pull_requests` / `get_pull_request_reviews` を **httpx モック**でテストする
      （`github_git_client.py` の既存 `get_*` テスト同様、レスポンス JSON を dataclass へマップする検証）。
- [ ] authorship 突合のテスト（login 一致 → `users.id` 解決 / 突合不能 → `None` フォールバック、`ctx.session` モック）。
- [ ] 依存抽出のテスト（Python / TS のサンプルから `(from_path, to_path)` が正しく生成され、外部パッケージが除外されること）。
- [ ] 方式 B のテスト（token が `GitHubAppService.get_installation_token` で mint され、ペイロード/ログに token が出ないこと）。

## 完了条件

- service から **commit 履歴・blame・PR レビューメタ** が取得でき、httpx をモックしたテストで dataclass へのマップが検証される。
- **authorship 突合**（GitHub login/email → `users.id`、不明時 `None`）が service ユーティリティとして提供され、テストが通る。
- **依存抽出ヘルパ**が import から `(from_path, to_path)` を生成し、026 の `dependency` 行に投入できる形であることがテストで確認される。
- 取得方式（REST/GraphQL vs clone）と File 同一性・dev 識別子の正規化が **ADR に記録**される。
- すべての履歴取得が **方式 B**（installation_id のみ搬送、service が Secret Manager から mint）で行われ、
  キュー/GCS/ログに token が残らない。
- バックエンド：`cd backend && uv run --directory service pytest` /
  `uv run ruff check shared/shared api/app service/service && uv run ruff format --check shared/shared api/app service/service` /
  `uv run ty check shared/shared api/app service/service` が通る。
- `CHANGELOG.md`（日本語）に `Added`（GitHubGitClient へ commit 履歴・blame・PR レビュー取得 / authorship 突合 /
  依存抽出ヘルパを追加）の追記。

## 対象外・保留

- **KC スコア式の確定・`file_kc` テーブル**（029 が所有）。本 issue は authorship/blame/依存の **取得手段** のみで、KC を算出しない。
- **コード負債／知識負債の検知ロジック**（028/030 が所有）。
- **配信 API**（031 の `GET .../debts`、032 の `GET .../galaxy`）と `client.ts` の mock 差し替え（連携先）。
- **新 JobType / 新パイプラインの登録**（`shared/shared/enums.py` `JobType` / `service/service/registry.py` は本 issue では不変）。
- **author↔user の永続マッピングテーブル**新設（必要なら ADR に記し 029 へ委譲）。
- **定期スキャン**（Cloud Functions/Pub-Sub）は 037。
- **pgvector による依存/概念類似検索**は将来（拡張有効化は 026、本実装は後続）。

## 参考

- 関連 issue
  - `docs/issue/026-backend-analysis-data-model-and-shared-tables.md` — `analysis_run` / `repo_file` / `dependency`・正規化 ADR（前提）
  - `docs/issue/028-backend-code-debt-detection-pipeline.md` — 本ヘルパで履歴/AI 痕跡を取得し負債検知（消費先）
  - `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — authorship/blame/依存抽出を KC 算出に使う（消費先・`file_kc`/`dependency` 所有）
  - `docs/issue/030-backend-knowledge-debt-detection-pipeline.md` — 著者離脱/未レビュー判定に PR/履歴を使う（消費先）
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — 方式 B・`process(request, ctx)`・`GitHubGitClient` 利用の雛形
  - `docs/issue/009-knowledge-galaxy-2d-map.md` — ワームホール（依存）の製品意味（`009:9,57-59,224-226`）
- 現行実装（拡張・参照対象）
  - `backend/service/service/services/github_git_client.py` — `GitHubGitClient`（REST tree/contents のみ `:76-185`、本 issue で履歴拡張）
  - `backend/service/service/services/github_app.py` — `GitHubAppService.get_installation_token`（方式 B token mint `:49-71`）
  - `backend/service/service/pipelines/stack_analysis.py` — `_mint_installation_token`（`:332-342`）/ `process(request, ctx)`（`:361-389`）
  - `backend/shared/shared/pipelines/context.py` — `PipelineContext`（`blob` / `session`）
  - `backend/api/app/api/v1/github.py` — `resolve_installation_id`（user → `github_login` 解決 `:88-101`）/ `InstallationIdDep`
  - `backend/shared/shared/models/tech_stack.py` — ORM 雛形（テーブルを足す場合の形）
- 契約・mock
  - `frontend/src/lib/api/schemas.ts:298-301` — `wormholeSchema`（`from` / `to` = 依存 = 抽出ヘルパの出力先）
  - `frontend/src/lib/api/schemas.ts:224-228` — `assignedDeveloperSchema`（`github_handle` / `coverage` / `certified_via` = authorship 突合の利用先）
- 規約
  - `CLAUDE.md` / `backend/CLAUDE.md` — 方式 B 厳守、Secret Manager 必須、Vertex AI + ADC（API キー不使用）、WIF、
    Annotated DI param 順序厳守、`uv run ruff/ty/pytest` ゲート、`CHANGELOG.md`（日本語, Keep a Changelog）
