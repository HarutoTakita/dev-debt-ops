# quiz / learning エンドポイントの認可ギャップ是正

## 概要 / 重大度

**重大度: High（IDOR + 状態遷移ガード欠落）。**

学習プラン生成とクイズの一部エンドポイントに所有権検証・状態遷移ガードの欠落がある。

## 該当箇所と問題

### A. IDOR: 任意の `attempt_id` の gap_concepts をプランへ取り込める（High）
- `backend/api/app/api/v1/learning.py:113-116` — `create_learning_plan` は `attempt_id`
  （`quiz_sessions.id`）から `QuizResult` を `session_id == attempt_id` で直接引く。
  `QuizResult` には `project_id`/`developer_id` が無く、`QuizSession` への join で
  「当該 project かつ当該ユーザのセッションか」を**検証していない**。
  他人/他 project の attempt の `gap_concepts` を自分のプランに混入でき、漏えいが永続化される。
- **修正**: `attempt_id` から `QuizSession` を読み、`qs.project_id == project.id` かつ
  `qs.developer_id == current_user.id` を検証（`quizzes._owned_session` を踏襲）。不一致は 404/403。

### B. `submit_quiz` に状態遷移ガードが無い（High）
- `backend/api/app/api/v1/quizzes.py:228-264` — 完了/採点中セッションでも無条件に
  `status="grading"` にして `QUIZ_GRADING` を再 enqueue 可能。
- **修正**: `if qs.status in ("grading", "completed"): raise HTTPException(409)`。
  `create_repayment_pr` の 409 ガードに倣う。

### C. `save_quiz_answer` が採点後の回答変更を許す（High）
- `backend/api/app/api/v1/quizzes.py:191-219` — `completed`/`grading` セッションにも upsert でき、
  採点後に回答を書き換えられる。
- **修正**: `grading`/`completed` 状態では 409。

### D. LearningPlan が project スコープのみで developer 所有が無い（Medium）
- `backend/api/app/api/v1/learning.py:148-161`（GET）/ `:169-195`（PATCH step）— プランは特定 developer の
  quiz gap 由来だが、org メンバなら誰でも取得・step トグル可能。クイズ系の `developer_id==current_user`
  より弱い。
- **修正**: `LearningPlan` に `developer_id` 列を追加（Alembic マイグレーション）し、取得/更新で所有者検証。
  もしくはリンク先 `quiz_session.developer_id` から所有を導出。共有モデルを採用する場合は意図を明記。

## 受け入れ条件

- A〜C のテスト（他人 attempt 403/404、completed への submit/answer が 409）を追加し緑。
- D: `LearningPlan.developer_id` 追加時はマイグレーション（chain 末尾に追番）+ throwaway DB で
  `alembic upgrade head` 検証、所有者検証テスト。
- backend gates（ruff/ty/pytest shared+api+service）緑。

## 対象外

- クイズ生成/採点パイプライン本体（034）の採点ロジック変更。
