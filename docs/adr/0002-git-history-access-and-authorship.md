# ADR 0002: git 履歴取得方式と authorship / 依存抽出の正規化

- ステータス: 採択（issue 027）
- 日付: 2026-06-19
- 文脈 issue: `docs/issue/027-backend-github-history-client-extension.md`
- 関連: [[ADR 0001]]（`docs/adr/0001-analysis-data-model-and-identity.md` — File 同一性・dev 識別子の親方針）

## 背景

028（コード負債）/ 029（KC 算出）/ 030（知識負債）は「誰がそのファイルを書いたか」「最後に触ったのは
いつか」「PR でレビューされたか」「ファイル間の import 依存（ワームホール）」を必要とする。だが現行
`GitHubGitClient` はツリー/内容取得しか持たず、履歴・blame・PR レビューに触れる経路が無い。本 ADR は
**履歴取得の方式**と、取得した author・依存を後続が join できる**正規形**を確定する。

## 決定

### 1. 履歴取得方式 — MVP は REST/GraphQL 拡張（方式 1）

- `GitHubGitClient` を拡張し、`list_commits`（REST `GET /commits`）/ `get_blame`（**GraphQL** `object(expression).blame(path)`、
  REST に blame が無いため）/ `list_pull_requests` / `get_pull_request_reviews` を追加する。
- 認証は既存の installation access token（`Authorization: Bearer`）を REST・GraphQL 共通で用いる。
- **ローカル clone（方式 2）は採らない**。採用する閾値は「対象リポジトリが大きく REST/GraphQL の
  installation レート上限に継続的に当たる」場合とし、その時のみ同一 dataclass を返す別実装
  （例 `GitCloneHistoryClient`）を新設して呼び出し側を差し替える。方式 2 では token を URL に埋めて
  shallow clone するため、**clone 一時データは処理後に必ず破棄**し、private ソースの残留を避ける。
- レート制限は各メソッドの `raise_for_status()` で顕在化させ、ページングは呼び出し側が `page` を進める
  （`list_branches` の per-page 上限規約に倣う）。バックオフの本格導入は方式 2 検討時に併せて行う。

### 2. authorship 突合 — `account_id` 主・`account_email` 従、login は非キー

- fastapi-users の `oauth_accounts` には **login 列が無い**（GitHub login は実行時に `/user` で解決する設計。
  `api/app/api/v1/github.py` の `resolve_installation_id`）。よってオフライン解析では login をキーにできない。
- 突合は **GitHub 数値 ID（`account_id`）を主キー**とする。これは commit/blame の `author.id`（REST）/
  `databaseId`（GraphQL）が提供する安定識別子で、login 変更に強い。次点で `account_email`（大文字小文字無視）。
- 突合不能（外部コミッタ等）は **`None`** を返し、呼び出し側は GitHub handle を生で保持する
  （[[ADR 0001]] の「`users.id` 主・login 従、null 可」原則に整合）。
- service コンテナは `app.*` ORM を import できないため、突合は `ctx.session` 上の **raw SQL**で
  `oauth_accounts` を引く（`service/service/services/authorship.py`）。
- **永続的な author↔user マッピングテーブルは本 issue では作らない**。`account_id`/`account_email` で不足が
  判明した場合に限り、それを実際に使う 029（KC が dev_id を埋める issue）で新設を検討する。

### 3. 依存抽出 — リポジトリ内エッジのみ、純粋関数

- import 解析は **リポジトリ内ファイル間の `(from_path, to_path)` エッジのみ**を返す。npm/PyPI 等の
  外部パッケージ・解決不能な specifier・自己参照は除外する。
- 言語別 parser（最小）: Python は `import` / `from`（相対 import はドット数=level でソースの package から解決、
  絶対 import はリポジトリ top 起点の first-party レイアウトを仮定）、TS/JS は相対 specifier のみ
  （`.`/`..`/`/` 始まり）を拡張子・`index.*` 補完で解決。
- 解決は「リポジトリ snapshot の path 集合」への所属判定で行う純粋関数（`dependency_extraction.py`）とし、
  I/O を持たない。出力は 026 の `dependency`（`run_id`/`from_path`/`to_path`）行へ投入できる構造体に揃える。
  **DML は 029 が `ctx.session` で行う**（本 issue は生成器のみ）。

### 4. 方式 B（token 受け渡し）の踏襲

- 履歴・GraphQL を含む全取得は 018 で確立した方式 B を厳守する: queue/GCS には `installation_id` のみ載せ、
  service が `GitHubAppService.get_installation_token` で Secret Manager の App 秘密鍵から token を mint する。
  token をペイロード/ログに残さない。

## 影響

- 028/029/030 は本 ADR の dataclass・突合関数・抽出関数を `process(request, ctx)` から呼ぶだけで
  履歴・authorship・依存を得る。テーブル所有は 026、配信 API は 031/032。
- 方式 2（clone）へ移る場合も、本 ADR の dataclass インターフェースと方式 B を保ち、ADR を追補する。
