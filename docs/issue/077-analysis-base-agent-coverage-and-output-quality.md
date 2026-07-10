# 解析: Base Analysis エージェントのカバレッジ・出力健全性

## 概要 / 重大度

**重大度: Medium〜High（精度）。** agent-first の Base Analysis（探索→著者）が「見る範囲が狭い」「空出力を
成功として無言受理」「対象ブランチ取り違え」など、根拠データの質を下げる箇所を是正する。#076（呼び出し層の
信頼性）と対で、こちらは**カバレッジと出力の妥当性**にフォーカス。

解析パイプライン横断レビュー（2026-07）由来。関連: #073–#076, #078。
確認度: **確認済** / **要確認**。

## 該当箇所と問題

### A. `{exploration}` が非 optional で `KeyError` → 探索成果が全消失（Medium・要確認）
- **該当**: `service/service/agents/base_analysis_tools.py:89`（author instruction の `{exploration}`）
- **問題**: ADK は explorer の最終イベントに text パートがある時のみ `output_key="exploration"` を session
  state に書く。explorer がツール呼び出しで終わる/空応答/予算短絡だと `exploration` が未設定となり、ADK の
  `inject_session_state` が `KeyError('Context variable not found: exploration.')` を送出。author run 全体が
  中断し、`agentic_analysis.py:165` の広い `except` が握り潰すため**探索成果ごと空で無言フォールバック**。
- **修正**: プレースホルダを optional に（`{exploration?}` → 欠落時は空文字）。加えて exploration が空なら
  明示的に決定的フォールバックへ短絡し「空で成功」を避ける。

### B. エージェントが見るのは先頭 20 ファイル × 5000 字だけ（High・確認済）
- **該当**: `service/service/agents/tools.py:19-20`（`_MAX_AGENT_FILES=20` / `_MAX_FILE_CHARS=5_000`）、
  `:95`（`sources[:_MAX_AGENT_FILES]`）、`:112-113`（read 切り詰め）
- **問題**: `list_repo_source_files` がフィルタ後**ツリー順で先頭 20 件**に切る（優先度付け無し）。非自明な
  リポジトリでは feature clustering・コード/理解負債の根拠が偏り、`read_file` の 5000 字上限と併せて
  総証拠量が概ね 20×5k 字＝リポジトリ規模に依らず固定になる。
- **修正**: 上限を引き上げ、かつホットスポット/複雑度/import 次数/サイズで優先選択（ツリー順の head-truncate を
  やめる）。必要時に追加取得できるページングも検討。

### C. owner/repo/branch がプロンプト散文のみで branch 取り違えの恐れ（Medium・要確認）
- **該当**: `service/service/agents/runner.py:75`、`base_analysis_tools.py:73-83`、既定引数
  `tools.py:80, 97`（`branch="main"` / `ref="main"`）
- **問題**: seed は owner/repo/branch を日本語文中に埋めるだけで、`list_repo_source_files(owner, repo, branch)`
  / `read_file(..., ref)` に**逐語で渡す**指示が無い。LLM が引数を省くと既定 `main` に落ち、非 `main` ブランチで
  **別ツリーを解析**しつつ成功に見える。
- **修正**: owner/repo/branch を構造化コンテキストとして明示し「必ずこの branch を使う（main に既定しない）」と
  指示、またはツールクロージャに束縛して branch を誤れないようにする。

### D. `stack_analysis.process()` が不安定な ADK エージェントで空 stack を COMPLETED にする（Medium・要確認）
- **該当**: `service/service/pipelines/stack_analysis.py:410-414`（`run_stack_analysis` 経由）
- **問題**: 標準の `process()` は自律 ADK エージェントを使うが、その兄弟 `populate_tech_stack` の docstring が
  「`classify_stack` 後に `save_stack` を呼ばず終える事がある＝テーブル空」と明言。その場合 `_read_persisted`
  が空を返し `process` は空 `languages`/`categories` で `COMPLETED` → 「技術スタックを学ぶ」学習セクションが空。
  （なお agentic バックボーンは決定的 `populate_tech_stack` を使う〔`agentic_analysis.py` の `_populate_stack`〕ため
  影響は**単体 stack-analysis ジョブ経路**に限定。要スコープ確認。）
- **修正**: `process()` も決定的 `populate_tech_stack`（list→read→classify→save）を使う、または保存行が非空で
  ある事を assert して不足なら fail/retry。

## 受け入れ条件

- A: explorer が text 無しで終わっても author が KeyError で落ちず、空なら決定的フォールバックへ（テスト）。
- B: 大きめリポジトリで先頭固定 20 件でなく優先度付き選択になる（テスト or レビュー）。
- C: 非 main ブランチ指定時に main を読まない（テスト）。
- D: 単体 stack 解析で空 stack を COMPLETED にしない（テスト）。
- backend gates 緑。

## 対象外

- 探索戦略の全面再設計・MCP ツールセットの追加。B の「上限値」は要ベンチ（コスト/精度のトレードオフ）で別途調整。
