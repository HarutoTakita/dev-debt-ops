# バックエンド堅牢性: GitHub レート制限 / ADK 出力ガード / N+1

## 概要 / 重大度

**重大度: Medium（堅牢性・一貫性・性能）。**

パイプライン横断の堅牢性改善。GitHub レート制限の非対応、ADK 出力の型ガード欠落（他ヘルパと不一致）、
api の N+1 クエリをまとめて是正する。

## 該当箇所と問題

### A. GitHub クライアントがレート制限/二次制限を扱わない（Medium）
- `service/service/services/github_git_client.py`（全メソッドが `raise_for_status()` のみ）。
- `knowledge_debt_detection.py:204-216`（ファイル×PR×レビューで O(n) REST 呼び出し）、
  `kc_analysis.py:189-193`、`learning_plan_generation.py:85-87` のループで 403/429 が出ると
  恒久エラー扱いで Job FAILED。`X-RateLimit-Remaining`/`Retry-After` を見ない。
- **修正**: クライアントで 403/429（二次制限）を transient エラーとして区別し、worker が 503 を返して
  Cloud Tasks に再試行させる（または `Retry-After` 尊重の backoff）。レビュー fan-out の上限/バッチ化も検討。

### B. ADK `analyze_tech_stack` が dict 以外の出力を素通し（Medium・一貫性）
- `service/service/services/gemini_stack_service.py:134-137` — `json.loads(response.text)` を
  そのまま返す。配列/スカラ（妥当 JSON・誤形）でも返り、`save_stack` の `.get(...)` で AttributeError。
  兄弟ヘルパ（`generate_quiz`/`grade_quiz`/`generate_refactor`）は `isinstance(raw, dict)` ガード済みで不一致。
- **修正**: `if not isinstance(raw, dict): return _empty_result()` を追加し他ヘルパと揃える。

### C. agent activity 配信の N+1（Medium・性能）
- `api/app/api/v1/agents.py:62-97,154-169` — `_activity_out` がステップ毎に evidence を個別クエリ、
  `list_activities` が activity 毎に `_activity_out`。O(activities × steps)。
- **修正**: `IN (...)` 一括取得 or `selectinload`（`learning.py:47-55` の一括取得パターンに倣う）。

### D. debt 一覧の N+1（Medium・性能）
- `api/app/services/debt_query.py:71-86,224-235` — `_code_out`/`_knowledge_out` が debt 毎に
  `AssignedDeveloper` を個別クエリ。
- **修正**: run の debt id 群で `AssignedDeveloper` を一括取得し `(debt_kind, debt_id)` でマップ。

### E. `dormant_days`/`author_left` が author 日付（偽造可能）依存（Low）
- `knowledge_debt_detection.py:50-58,219`、`learning_plan_generation.py:45-49` — git author 日付
  （`github_git_client.py:291`）はコミッタのローカル時計で偽造可能。
- **修正**: committer 日付 / GitHub のコミットタイムスタンプを優先し、未来日付をクランプ。

### F. ADC クライアントの同期 discovery を毎回実行（Low）
- `gemini_stack_service.py:90-110` — `google.auth.default()` を async 経路で毎回同期実行（event loop ブロック）。
- **修正**: クライアント/認証をキャッシュ、または discovery をスレッドへ。

## 受け入れ条件

- A: mock client で 429 を返すと worker が transient（503/再試行）として扱う（テスト）。
- B: 非 dict 出力で `_empty_result()` を返す（テスト）。
- C/D: 取得クエリ数が固定（activity/debt 件数に比例しない）ことを確認（クエリ数アサート or レビュー）。
- backend gates（ruff/ty/pytest shared+api+service）緑。

## 対象外

- 検知/KC ロジックの精度改善、SSE/WebSocket 化。
