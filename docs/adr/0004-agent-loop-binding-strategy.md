# ADR 0004: Twin Agent 自律ループの束ね戦略（read-and-narrate）

- ステータス: 採択（issue 036）
- 日付: 2026-06-20
- 文脈 issue: `docs/issue/036-backend-agents-autonomous-loop-and-narrative.md`
- 関連: [[ADR 0002]]（git 履歴取得・方式 B）、[[ADR 0003]]（KC）

## 背景

`code_debt_loop` / `knowledge_debt_loop` は「検知 → 分析 → 計画 → 返済 → 検証」の 5 ステージを束ね、
一人称ナラティブと考古学的根拠を生成して可視化する。検知（028/030）・KC 算出（029）・返済 PR（033）・
クイズ生成（034）は別パイプラインが所有する。ループがそれらを **(a) sub-enqueue** するか **(b) ループ内で
直接呼ぶ** か、あるいは **(c) 既存結果を読むだけ** かを決める必要がある。

## 決定（MVP）

- **検知系（028/029/030）はループ内で「結果を読むだけ」**（read-and-narrate）。ループは最新の
  `analysis_run`（該当 `kind` の検知）と `code_debts` / `knowledge_debts` を読み、Gemini で一人称
  `message` + `evidence`（first_commit / ai_generated / adr_reference / pr_review）を生成して
  `agent_pipelines` / `agent_activities` / `narrative_steps` / `narrative_evidence` に永続化する。
  検知を**再実行しない**（重複・実行時間・冪等の観点で、検知は検知パイプラインが所有）。
- **生成系（033 返済 PR / 034 クイズ）の起動（`repay` ステージ）は MVP では行わない**。`repay` / `verify`
  ノードは `pending` のままとし、実際の生成は既存エンドポイント（`POST .../debts/{id}/repayment-pr` /
  `POST .../quizzes/generate`）が担う。将来、ループから **sub-enqueue**（新 Job を Cloud Tasks に投げ、
  ループ Job は pending/完了を記録）する形に拡張する。`PipelineContext` には dispatcher が無いため、
  sub-enqueue を入れる際は context 拡張（dispatcher 注入）が前提作業になる旨をここに記す。
- ループは GitHub を直接叩かない（MVP）。git 履歴由来の根拠は 028/030 が `archaeology_notes` /
  `detection_notes` に既に取り込んでいるため、それを evidence に流用する（[[ADR 0002]] の取得層の重複呼び出しを避ける）。

## 冪等性

- `agent_pipelines.job_id` でループ Job を一意化し、at-least-once 再配送では既存の pipeline/activity を返す
  （`shared.worker.run_task` の Job 冪等性に加え、ナラティブの二重生成を防ぐ）。

## 影響・未確定

- `repay`/`verify` の自動起動（sub-enqueue）と CI 自己確認の実体は将来 issue。`evidence.href` は
  `/matrix/{debt_id}` 形式で Matrix 詳細へクロスリンクする（フロントがプロジェクト配下へ解決）。
- 定期トリガー（ループの定期起動）は Cloud Functions/Scheduler（廃止された 037 の範囲だったため、別途検討）。
