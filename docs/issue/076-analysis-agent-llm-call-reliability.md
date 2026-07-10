# 解析: ADK / Gemini 呼び出しの信頼性（retry・parse・budget・leak）

## 概要 / 重大度

**重大度: Medium（信頼性・コスト）。** Base Analysis エージェントと各 Gemini ヘルパの呼び出し層に潜む、
再試行の取りこぼし・空応答パースのクラッシュ・予算/コンテキストの制御不足・リソースリークを是正する。
先日のレート制限対策（#045 系のジッター/バックオフ）の続き。

解析パイプライン横断レビュー（2026-07）由来。関連: #073–#075, #077, #078。
確認度: **確認済** / **要確認**（実装前に再検証）。

## 該当箇所と問題

### A. リトライ対象から 502/504/408 が漏れている（Medium・確認済）
- **該当**: `service/service/agents/model.py:13`（`_AGENT_RETRY_STATUS = [429, 500, 503]`）
- **問題**: genai 既定の再試行集合 `(408, 429, 500, 502, 503, 504)` を上書きしており、Vertex ゲートウェイの
  **502 Bad Gateway / 504 Gateway Timeout が再試行されず run 中断**（`hooks.py:20` が警戒する 502/timeout の
  ケースそのもの）。クライアント側 `httpx.TimeoutException`/`ConnectError` は無条件再試行されるので穴は 502/504/408。
- **修正**: `_AGENT_RETRY_STATUS` に 502, 504, 408 を追加（または `http_status_codes` を渡さず既定継承）。
  バックボーン側 `gemini_stack_service._generate` の再試行集合とも突き合わせる。

### B. `json.loads(response.text)` が None で `TypeError` 未捕捉（Medium・確認済）
- **該当**: `service/service/services/gemini_stack_service.py:204`（および 257, 335, 409, 428, 471, 520, 564, 600）
- **問題**: 捕捉は `(json.JSONDecodeError, AttributeError)` のみ。候補が safety ブロック / MAX_TOKENS 切れで
  `response.text` が `None` だと `json.loads(None)` が `TypeError` を送出（未捕捉）→ ステップ中断。大出力系
  （`generate_quiz` :409、full 番号付きファイル content を送る `generate_code_walkthrough` :564）が最も露出。
  一部の呼び出し元はローカル try で包むが、包まない経路もある。
- **修正**: 共通パスで `text = response.text or ""; if not text: return <empty>` ガード、または except に
  `TypeError, ValueError` を追加。

### C. 共有 `RunBudget` が author の `save_base_analysis` を枯渇させる（Medium・要確認）
- **該当**: `service/service/agents/hooks.py:32-37`、`service/service/agents/base_analysis_tools.py:209, 219`
- **問題**: 同一 `budget` が explorer と author の `before_tool_callback` を駆動。`max_tool_calls=80` 超過で
  **全ツール**が短絡され、author の**終端 `save_base_analysis` まで**弾かれる（Serena/GitHub/CGC で 80 は容易に到達）。
  結果 `captured` が空 → `build_base_analysis` が空 `BaseAnalysis` → `is_empty()` が「何も無い→フォールバック」
  として無言で受理され、探索の成果が全て無駄になる（`max_model_calls=60` 経由でも同様）。
- **修正**: 終端 confirm 系ツール（`save_base_analysis`/`save_*`）を tool-call 予算から除外、または author 段の
  ヘッドルームを確保（sub-agent 毎に別/入れ子予算）。

### D. `RunBudget` がトークンを計測せずコンテキスト溢れの恐れ（Low・要確認）
- **該当**: `service/service/agents/budget.py:24-29`、`hooks.py:21`
- **問題**: 予算は tool/model/file の**件数**のみで、トークン/文字量を見ない。各ツール結果は
  `_MAX_TOOL_RESULT_CHARS=12_000` まで保持され多ターン履歴に累積・毎回再送されるため、`max_model_calls=60`
  近辺で 1 リクエストが数十万字規模になりコンテキスト窓超過（ハードエラー）や無制限コスト増を招きうる。
- **修正**: 保持ツール結果の累積文字/トークン予算を追加し、接近時に停止 or 履歴を圧縮。

### E. `run_analysis_agent` が例外時に trace / 部分結果を破棄する（Low・要確認）
- **該当**: `service/service/agents/runner.py:77-84`
- **問題**: `run_async` が例外を投げると `finally` が toolset を閉じて再送出し、`return recorder.trace,
  build_base_analysis(captured)`（:84）に到達しない。呼び出し側は既に記録済みの有用な `recorder.trace` を
  `[analysis_agent] failed: {exc}` 1 行に置換し（`agentic_analysis.py:170`）、author が save 済みかもしれない
  部分 base 解析も捨てる。診断価値と部分結果を失う。
- **修正**: `run_analysis_agent` 内で捕捉（または `finally` から return）し、失敗時も `recorder.trace` と
  `build_base_analysis(captured)` を返す。

### F. MCP toolset が try/finally の外で生成される（Low・要確認）
- **該当**: `service/service/agents/runner.py:53-65`（生成）対 :77-83（`finally` の `close()`）
- **問題**: serena/github/code_graph の toolset 生成・`build_analysis_agent`・`create_session` は `try` 前に
  実行され、`finally` の `toolset.close()` に守られるのは `run_async` ループのみ。`build_analysis_agent` /
  `create_session` が投げると接続開始済み toolset が閉じられず MCP stdio サブプロセスがリークしうる
  （遅延接続なので窓は狭いが構造が脆い）。
- **修正**: toolset 生成を `try` 内へ、または生成〜run を単一 try/finally で包み `close()` を必ず走らせる。

### G. `SecretRedactionPlugin` が会話全体を毎回再スキャンする（Low・要確認）
- **該当**: `service/service/agents/plugin.py:65-73`
- **問題**: `before_model_callback` が毎モデル呼び出しで `llm_request.contents` 全テキストを `deidentify`。
  ADK は毎ターン全履歴を再送するため早期パートを O(turns²) で再マスク。`DLP_ENABLED=true` だと Cloud DLP 呼び出し・
  レイテンシ・コストが増幅し DLP クォータに触れうる。`self.redacted` も二重計上（DLP 失敗時はルールベースに
  フォールバックするのでハードクラッシュはしない）。
- **修正**: 各ターンは**新規追加分のみ**マスク（既スキャン済み末尾以降）、または part の identity/hash で
  memoize。

## 受け入れ条件

- A: 502/504 を返す mock で run が再試行される（テスト）。
- B: `response.text=None` で `_empty_result()` 相当を返し中断しない（テスト）。
- C: explorer が予算を使い切っても `save_base_analysis` が通る（テスト）。
- E: `run_async` 例外時にも trace/部分 base 解析が返る（テスト）。
- backend gates（ruff / ty / pytest）緑。

## 対象外

- ADK/genai の SDK 自体の挙動変更、SSE/ストリーミング化。トークン予算の厳密な課金モデル化（D は上限ガードのみ）。
