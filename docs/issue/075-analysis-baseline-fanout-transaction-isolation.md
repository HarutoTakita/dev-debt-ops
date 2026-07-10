# 解析: baseline fanout のトランザクション分離 / 冪等性

## 概要 / 重大度

**重大度: High（データ整合性・信頼性）。** 機能ごとに学習プラン + baseline クイズを生成する fanout
（`baseline_generation`）が**単一 session・セーブポイント無し**で回るため、1 機能の失敗が他機能を巻き込む/
半端な生成物が永続化されて冪等ガードで再生成もブロックされる。分離境界（savepoint）と重複防止を入れる。

解析パイプライン横断レビュー（2026-07）由来。関連: #073, #074, #076–#078。

## 該当箇所と問題

### A. 機能単位のセーブポイントが無く、失敗が連鎖 / 半端な生成物が永続化される（High・確認済）
- **該当**: `service/service/pipelines/baseline_generation.py:174-189`、
  `service/service/pipelines/learning_plan_generation.py:63-69`（`LearningPlan` の flush）、
  コミットは `shared` の `run_task`（終端で 1 回）
- **問題**: fanout は `ctx.session` 1 つを共有し、機能ごとに `try/except ... continue` で「1 機能失敗で全体を
  止めない」意図。しかし
  - (a) 失敗が **DB レベル**（flush 時の `IntegrityError` / 制約違反など）だと async session が
    rollback-required 状態になり、以降の機能の最初の `session.execute()` が `PendingRollbackError` で連鎖失敗
    → 分離の意図が崩れる。
  - (b) **非 DB 失敗**（`_generate_plan` 内で `LearningPlan` と一部 `LearningResource` を flush 済みの後に
    Gemini が失敗）だと、その中途行が**終端 commit で確定** → 半端なプランが永続化。冪等ガード
    （`existing is not None` → skip）が再生成をブロックし、ユーザーは空/部分プランに固定される。
- **修正**: 機能ごとの plan/quiz を savepoint で包む — ループ内で `async with session.begin_nested():`。
  失敗時はその機能の行（作成した `LearningPlan` 含む）だけロールバックし、session を再利用可能に保つ。

### B. 完了済み baseline クイズが再解析で重複生成される（Low・要確認）
- **該当**: `service/service/pipelines/baseline_generation.py:94-106`
- **問題**: 既存判定が `status != "completed"` を除外＝**未完了の baseline のみ skip**。学習者が baseline を
  完了した後に再解析すると、同じ `(project, developer, feature)` に 2 つ目の `is_baseline=True` セッションが
  作られ生成される。progress / baseline-KC の二重計上につながる。
- **修正**: `(project, developer, feature)` に **completed 含め baseline が 1 つでもあれば skip**、
  または明示的な retake フローの背後にのみ再生成を許可。

## 受け入れ条件

- A: 1 機能で DB 例外を注入しても残りの機能が生成される（`PendingRollbackError` 連鎖が起きない）／
  Gemini 失敗時に半端な `LearningPlan` が永続化されず、再解析で再生成できる（テスト）。
- B: baseline 完了後に再解析しても baseline セッションが重複しない（テスト）。
- backend gates（ruff / ty / pytest）緑。

## 対象外

- fanout の並列化（現状は逐次）や、学習プラン/クイズ生成ロジック自体の変更（#074 の範囲）。
- `run_task` のコミット戦略（1 ジョブ 1 コミット）自体は不変（#042 の設計を踏襲。savepoint は互換）。
