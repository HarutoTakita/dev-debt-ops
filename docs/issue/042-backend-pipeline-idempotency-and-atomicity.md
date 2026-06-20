# 解析パイプラインの冪等性・原子性の是正（stale 行 / commit 境界）

## 概要 / 重大度

**重大度: High（at-least-once 配信下での誤結果・不整合）。**

検知/KC/採点/プラン/ループ各パイプラインは「run を job_id で再利用 + upsert」で冪等を謳うが、
(1) 再実行時に **stale 行を削除しない**、(2) **`process` 内で独自に commit** するため Job 状態と
ドメイン行が非原子、(3) 部分失敗後の再配信で副作用が再走する。Cloud Tasks の at-least-once
配信下で誤った/古い結果を返し得る。

## 該当箇所と問題

### A. 再実行で stale 行が残る（High）
- `service/service/pipelines/code_debt_detection.py:124-143,220-234`、
  `knowledge_debt_detection.py:98-116,240-287`、`kc_analysis.py:90-108,213-254`。
- run を再利用しつつ findings を upsert のみ。閾値低下/ファイル削除/AI フラグ減で**消えるべき行**が
  残る。結果サマリ（`detected`/`by_type`/`by_severity`）は現行 findings からのみ算出され、テーブル実体と乖離。
- **修正**: run スコープで「delete-then-insert」または「現在の finding 集合に無い行を削除」を同一
  トランザクションで実施（`run_id` キー）。

### B. `process` 内 commit による非原子性（High）
- `stack_analysis.py:230-231`、`code_debt_detection.py:234`、`knowledge_debt_detection.py:287`、
  `kc_analysis.py:258`、`quiz_*`、`learning_plan_generation.py:170`、`agent_loop.py:186` が
  `process` 内で `await session.commit()`。`shared/shared/worker.py:94-98` は Job を別途 commit。
  間で例外が起きるとドメイン行は durable だが Job は FAILED/PROCESSING → 「失敗ジョブなのに
  AnalysisRun は COMPLETED で全 findings」という観測可能な不整合。
- **修正**: `process` 内 commit を撤廃し、`run_task` が唯一の終端 commit を所有（ドメイン行 + Job 状態を
  原子化）。これで A の delete-then-insert も実装容易になる。
- 注意: `PipelineContext.session` の commit 責務を明確化し、各パイプラインの docstring を実態に合わせる。

### C. 弱い冪等ガード（COMPLETED のみ）（Medium）
- `shared/shared/worker.py:63-98` — `status == COMPLETED` のみスキップ。FAILED/PROCESSING の
  再配信は `process` を頭から再走。B の原子化を前提に、再利用 run を「再開点」として扱う。

### D. 再配信時の result_data の誤報告（Medium）
- `agent_loop.py:122-130` — 冪等分岐が `steps=0` 固定で返し、既存 `NarrativeStep` 数と矛盾。
  → 既存ステップ数を数えて返す。
- `quiz_grading.py:55-58` — 完了セッション再配信で `kc_before=0.0, kc_after=score` を返し、
  実 KC（`quiz_results`）を破棄。→ `QuizResult` を読み直して echo。

### E. `analysis_runs.branch` の NOT NULL に server_default が無い（Medium・関連）
- `shared/shared/models/analysis_run.py:40`（`default="main"` は Python 側のみ）vs
  `api/app/alembic/versions/0006_*.py:34`（server_default 無し）。
  非 ORM insert（構築済み statement）で NOT NULL 違反の恐れ。
- **修正**: マイグレーションに `server_default=sa.text("'main'")` を追加（chain 末尾に是正
  マイグレーション）し、モデルの `sa_column`/`server_default` を揃える。

## 受け入れ条件

- 同一 job_id 再実行で stale 行が消えること（テスト: 1回目に出た debt が条件変化で2回目に消える）。
- `process` 内 commit 撤廃後も全パイプラインのテストが緑（shared/api/service pytest）。
- D の再配信で正しい step_count / kc が返る（テスト）。
- E のマイグレーションを throwaway DB で `alembic upgrade head` 検証、down も検証。
- ruff/ty 緑。

## 対象外

- 検知/KC/採点の解析ロジック自体の精度改善。
