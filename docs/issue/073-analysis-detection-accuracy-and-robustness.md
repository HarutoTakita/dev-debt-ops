# 解析: 検知パイプラインの精度・堅牢性（コード負債 / KC / 理解負債）

## 概要 / 重大度

**重大度: High〜Low（混在）。** 決定的バックボーンの検知系（`code_debt_detection` / `kc_analysis` /
`knowledge_debt_detection` とその supporting services）に潜む、**成功に見えて出力が静かに劣化するバグ**と
クラッシュ潜在をまとめて是正する。A は agentic 解析で日常的に発火する精度劣化。

本ドキュメントは解析パイプライン横断レビュー（2026-07）由来。関連: #074–#078（同一レビュー）。
各項目の確認度: **確認済**＝実コードで確認 / **要確認**＝レビュー指摘・実装前に再検証すること。

## 該当箇所と問題

### A. AI 生成確率が Trivy パスの `KeyError` で全件 0.0 になる（High・確認済）
- **該当**: `service/service/pipelines/code_debt_detection.py:379-392`
- **問題**: `flagged_paths` に **Trivy が検出したロックファイル/マニフェスト**（`files` に含まれない
  パス。`_trivy_to_findings` の docstring 自身が「fetched source set に無い」と明言）が混ざり、
  `{p: files[p] for p in flagged_paths}` が `KeyError` → 直後の `except Exception` で握り潰し →
  `ai_probs={}` → 全 finding の `ai_generation_prob` が 0.0 に固定。agentic では Trivy が常時走り
  マニフェストを頻繁に検出するため、多くの実解析でこの経路に落ちる。
- **修正**: 内包表記を `{p: files[p] for p in flagged_paths if p in files}`（または `files.get(p, "")`）に。

### B. cyclomatic complexity 正規表現の過大カウント（Medium・要確認）
- **該当**: `service/service/services/code_analysis.py:126-145`
- **問題**: 判定キーワード正規表現を**生テキストに直接**適用（コメント/文字列を除去しない）。
  `_JS_DECISION` は `\?\??` で TS の optional 型（`name?: string`）・optional chaining（`a?.b`）・
  nullish 合体まで数え、`_PY_DECISION` は文字列/コメント内の `and`/`or`/`if` も数える。型付けが厚いだけの
  単純な TS ファイルや、キーワードを多く含む文字列を持つ Python が `_COMPLEXITY_MIN=8` を超え、
  実体のない complexity 負債として検知・スコア化される。
- **修正**: 照合前にコメント/文字列を除去（`_normalized_lines` 相当を再利用）、TS 三項は `\s\?\s` 等に限定。

### C. 「最新 KC run」を COMPLETED で絞っていない（Medium・要確認）
- **該当**: `service/service/pipelines/knowledge_debt_detection.py:70-81`（`kc_analysis` の run 選択も同様）
- **問題**: プロジェクトの `kc_analysis` run を `created_at` 降順の先頭で選ぶだけで status を見ない。
  より新しい `PROCESSING`/`FAILED` の失敗 run が選ばれると `file_kc` が空/部分となり、
  `knowledge_coverage` / `assigned_developers.coverage` が無言で 0.0 に落ち、二軸マトリクスが破損する。
- **修正**: `where` に `AnalysisRun.status == JobStatus.COMPLETED` を追加。

### D. 内容取得失敗ファイルが `init_kc=0.9`（star/理解済み）扱いになる（Medium・要確認）
- **該当**: `service/service/pipelines/kc_analysis.py:307` ＋ `_initial_kc_factor`（:73-81）
- **問題**: `files` は `content is not None` のパスのみ保持するが blame は全パスで取得。`files` に無いパスは
  `files.get(path, "")` → `""` → `lines=0` → 最小行分岐で `shape=1.0` → `_KC_INITIAL_MAX=0.9` を返す。
  読めない/大きすぎる/バイナリ寄りのファイルが「些末な定型 = 理解済み」と逆評価され、
  「大きく複雑 ⇒ 理解負債ホットスポット」という設計意図の反転になる。
- **修正**: 「未取得ゆえの空」と「本当に小さい」を区別し、`path not in files` はサイズ推定をスキップ
  （floor / unexplored 扱い）。

### E. login 無しの未マッチ著者が集約行スロットと衝突する（Medium・要確認）
- **該当**: `service/service/pipelines/kc_analysis.py:308-338`（集約 upsert は :328、部分索引は :237-243）
- **問題**: `resolve_author_user_id` が `None` かつ `identity.login` も空（email-only committer / 削除済み
  アカウント）の場合、`_upsert_file_kc(dev_id=None, github_handle=None)` が集約ブランチへ分岐し、
  集約書き込みと同じ unique key `(run_id, file_path)` に衝突。per-dev 行が集約スロットに入り真の集約で上書き
  → その著者は dev 行から欠落する一方 `file_kc_count` は加算済みで件数が水増しされる。
- **修正**: `dev_id`/`github_handle` が両方 `None` のときは dev upsert をスキップ（または安定ハンドルを合成）。

### F. `_age_days` が naive datetime で `TypeError` クラッシュ（Low・確認済／潜在）
- **該当**: `service/service/pipelines/knowledge_debt_detection.py:53-61`
- **問題**: `except ValueError` のみ。TZ 無し `authored_at`（Z/offset 無し）だと `fromisoformat` が naive を返し、
  aware な `now` との減算で `TypeError` が未捕捉 → 理解負債ステップ全体が失敗。GitHub は通常 Z 付きのため潜在。
- **修正**: `except (ValueError, TypeError)`、および naive は `replace(tzinfo=UTC)` で補完してから減算。

### G. カンマ区切り `import` の取りこぼし（Low・要確認）
- **該当**: `service/service/services/dependency_extraction.py:22, 112-118`
- **問題**: `_PY_IMPORT = r"^\s*import\s+([.\w]+)"` は 1 モジュールしか捕捉せず、`import a, b` / `import p.x, p.y`
  の 2 つ目以降のリポジトリ内エッジが欠落。依存/ワームホールグラフが痩せ、dead-file 検知・feature clustering の
  コミュニティ成長が弱まる。
- **修正**: `import` 行の残りをカンマ分割し（`as` エイリアス除去）各モジュールを解決（`from ... import` 側に倣う）。

## 受け入れ条件

- A: Trivy 由来のマニフェストパスが含まれても `ai_generation_prob` が正しく算出される（テスト）。
- C: COMPLETED でない KC run が最新でも、直近 COMPLETED の file_kc に対して coverage を結合する（テスト）。
- D/E: 未取得ファイルが high-KC(star) にならない／login 無し著者で集約行が壊れない（テスト）。
- F/G: naive 日時で落ちない／カンマ import が全モジュール解決される（テスト）。
- backend gates（ruff / ty / pytest shared+api+service）緑。

## 対象外

- 検知アルゴリズム自体の設計変更（スコア式の再定義など）。B の complexity は誤カウント是正のみで、
  真の複雑度指標（AST ベース）への置換は #061 の範囲。
