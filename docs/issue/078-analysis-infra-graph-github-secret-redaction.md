# 解析: データ基盤（コードグラフ / GitHub 取得 / 秘密情報マスク / クローン）

## 概要 / 重大度

**重大度: High〜Medium（正確性・セキュリティ・信頼性）。** 解析に食わせる元データの取得・整形・スクラブ層の
問題を是正する。A は暖機済み Cloud Run インスタンス間での**別リポジトリ混線**の恐れ、G は秘密情報の**LLM 平文
流出**の恐れがあり、いずれも影響が大きい。

解析パイプライン横断レビュー（2026-07）由来。関連: #073–#077。
確認度: **確認済** / **要確認**。

## 該当箇所と問題

### A. CodeGraph が固定グローバル KuzuDB パスで別リポジトリと混線する（High・要確認）
- **該当**: `service/service/services/code_graph.py:40-48`（`KUZUDB_PATH` がコンテナ固定）、
  `:60-67`（`cgc index`）、`:220-262`（`extract_snapshot` の Cypher が repo 非スコープ）
- **問題**: KuzuDB がコンテナ 1 個の**グローバルパス**に固定され、スナップショット照会は `(:File)` 等を
  **DB 全体**で拾う（`repo_dir` フィルタ無し）。docstring 自身が「path-scoping は将来」と認める通り、暖機済み
  インスタンスの 2 本目のジョブが**前リポジトリのノード/エッジを混入**（同名 `src/index.ts` で誤クロスエッジ）。
  Cloud Run concurrency > 1 の同時実行でも埋め込み DB を破壊しうる。
- **修正**: run 毎に一意な KuzuDB パス（clone 一時ディレクトリ由来）へ index し照会/MCP をそこへ向ける。
  または index 前に DB をリセット＋サービス concurrency を 1 に固定。グローバル 1 個を跨ぎ共有しない。

### B. `_cgc_query` の stdout 括弧スライスが脆く、グラフ全体を落としうる（Medium・要確認）
- **該当**: `service/service/services/code_graph.py:104-113`
- **問題**: stdout を最初の `[` から最後の `]` までスライスして `json.loads`。CGC CLI が
  `[INFO] indexing…` のような角括弧付き前置きを stdout に出すと `find("[")` がそれに食いつき非 JSON となって
  パース失敗 → **全 CGC 照会が無言で空** → グラフは決定的スナップショット（関数ノードのみ、cross-file
  CALLS/IMPORTS 無し）に無告知でフォールバック。
- **修正**: `--output` で JSON をファイル出力、または前置き行を除去して堅牢にパースし、非空だが解析不能な
  stdout はログする。

### C. shallow clone がエラー時に一時ディレクトリ残留（Medium・確認済）
- **該当**: `service/service/pipelines/agentic_analysis.py:138-176`
- **問題**: `shallow_clone`（:138）の後、`repo_dir` クリーンアップの `try/finally`（:152〜、`rmtree`）**より前**に
  グラフ構築・`_persist_code_graph`（DB 例外あり得る）・`trivy_scan.scan_repo` を実行。ここで例外が出ると
  `finally` 到達前に抜け**クローン残留** → 失敗反復で ephemeral ディスク逼迫。
- **修正**: `shallow_clone` が非 None を返した直後から `try/finally` で囲み、グラフ/persist/Trivy を内側に入れる。

### D. GitHub インストールトークン未更新で長時間 run が 401（Medium・要確認）
- **該当**: `service/service/services/github_git_client.py:148-159`、`github_app.py:49-71`、
  共有クライアント生成 `agentic_analysis.py:184`
- **問題**: トークンをヘッダに**恒久固定**し再発行しない。インストールトークンは約 1 時間で失効。1 回の agentic
  run は clone(〜180s)+cgc index(〜300s)+Trivy(〜180s)+エージェント+バックボーン+機能別 Gemini 生成で TTL 超過
  し得、後半の GitHub 読取が 401 → 生成テーブルが無言劣化。`github_app` は 300s バッファでキャッシュするが、
  稼働中クライアントへ再注入する経路が無い。
- **修正**: クライアントにトークンプロバイダ（or `GitHubAppService` 参照）を持たせ期限前に再取得、
  401 検知でクライアント再生成。

### E. `get_repository_tree` が `truncated` を無視し部分ツリーで続行（Medium・要確認）
- **該当**: `service/service/services/github_git_client.py:231-247`
- **問題**: 再帰 tree API は大規模リポジトリ（〜10万エントリ/7MB）で `truncated: true` を返すが、コードは
  `data.get("tree", [])` をそのまま使う。以降の全消費者（clustering / KC / dead-file / 決定的スナップショット）が
  不完全なファイル集合で動作し、欠落ファイルは「存在しない」ように見える（無警告）。
- **修正**: `data.get("truncated")` を確認し、true なら warn＋サブツリー逐次取得へフォールバック（最低でも
  「部分ツリー」フラグを surface）。

### F. `get_file_content` が >1MB / 非 UTF-8 を無言でドロップ（Medium・要確認）
- **該当**: `service/service/services/github_git_client.py:249-270`
- **問題**: デコードは `encoding == "base64"` かつ content 有りの時だけ。1〜100MB のファイルは
  `encoding: "none"`・空 content で返り、非 UTF-8 は strict デコードで `UnicodeDecodeError` → いずれも
  `content=None`＝本物のバイナリと**区別不能**。手書きの大きなソースが取得不能扱いで無言消失。
- **修正**: `size > 1MB` / `encoding == "none"` は blobs/raw media API で取得、「バイナリ」と
  「サイズ超過/デコード不能」を区別して呼び出し側が判断できるように。

### G. 秘密情報の許可リストが部分一致で、本物の秘密を LLM に漏らす（High・確認済／セキュリティ）
- **該当**: `service/service/services/secret_redaction.py:77-86`（`_is_allowlisted`）
- **問題**: 判定が `value in token or token in value` の**双方向部分一致**。許可リストは owner/repo/branch を含むため、
  ブランチ `main`/短い owner を**部分文字列として含む高エントロピー秘密**（例 `AKIAmain…`）が「許可」扱いとなり
  **マスクされず Gemini に平文送信**。detect-secrets（新規/高エントロピー捕捉）層を無効化する。本リポジトリの
  `main`/`develop` ブランチ名がまさに衝突例。
- **修正**: 許可リストは**完全一致**（or 語境界一致）にし、許可トークンに最小長を要求。3〜4 字のスラッグが
  部分一致するだけで秘密全体を素通しにしない。

### H. 代入パターンの部分一致で無害コードを過剰マスク（Medium・確認済）
- **該当**: `service/service/services/secret_redaction.py:57-65`（`_ASSIGNMENT_PATTERN`）
- **問題**: key グループが `[\w.\-]{0,40}?(?:…|token|…)[\w.\-]*` で、`tokenizer = "gpt2-large"` /
  `secret_sauce = …` / `api_keyboard_layout = …` のような**キーワードを部分に含むだけの識別子**まで一致し、
  6 字以上の値が `«REDACTED»` に。実在の非秘密ソース行が Gemini 到達前に破壊され解析品質が落ちる。
- **修正**: キーワードを key 内の**独立トークン**（語境界/区切り区切り）として要求し、`token→tokenizer` 等の
  よくある誤検出語幹を除外。

## 受け入れ条件

- A: 2 リポジトリを同一プロセスで連続解析してもグラフが混線しない（run 毎パス or リセットのテスト）。
- C: グラフ/persist/Trivy で例外を注入してもクローンが残らない（temp dir リークのテスト）。
- G: ブランチ名を部分に含む高エントロピー値がマスクされる（テスト）。
- H: `tokenizer=`/`secret_sauce=` 等がマスクされない（テスト）。
- D/E/F: トークン失効・truncated・大/非 UTF-8 ファイルが検知/フォールバックされる（テスト）。
- backend gates（ruff / ty / pytest）緑。

## 対象外

- CGC（CodeGraphContext）本体の改修、GitHub API のフル移行。DLP 有効時の詳細チューニングは #076-G と連携。
