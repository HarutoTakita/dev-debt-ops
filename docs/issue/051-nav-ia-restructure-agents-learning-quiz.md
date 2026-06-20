# ナビ/IA を再編する（エージェントビュー廃止 + 学習・クイズ統合）

## 概要
ナビゲーションを簡素化する。(1) 独立した「エージェント」ビューを**廃止**し、エージェント/解析ループの状況はダッシュボード（観測台）に集約する。(2) 機能の近い「学習」と「クイズ」を**1 セクションに統合**し、理解負債のある領域に対して「学習して input する／クイズで output する」という構成にする。

## 背景・目的
- エージェントの独立ビューは冗長: 解析の進捗はダッシュボードで見せれば足り、解析結果はマトリクス／クイズ／学習プランとして既に可視化される。専用タブは情報の二重化と「Coming Soon 風の孤立タブ」を生む。
- 学習とクイズは表裏一体（知識負債の input と output）。別タブだと「理解が足りない領域をどうするか」という導線が分断される。
- ナビ項目数を減らし、コアループ（診断→学習/クイズ→検証）を一本の物語として読ませる。

## タスク

### A. エージェントビューの廃止 → ダッシュボード集約
- [ ] `nav.ts` の `understand` セクションから `agents` 項目を削除する。
- [ ] エージェント/解析ループの状況を観測台に集約: ダッシュボードに「解析ラン状況カード」（直近のパイプライン/ループ状態・最終実行）を設け、`agent-store` の有用部分を流用する。
- [ ] `/[org]/[project]/agents` ルートは廃止 or リダイレクト（既存ディープリンク `analysisRun` の `loop_agents.deepLink` を観測台へ振り替える）。
- [ ] 不要化する `components/agents/*` を整理（ダッシュボードへ移すものと削除するものを仕分け）。

### B. 学習・クイズの統合
- [ ] 新セクション（例「知識負債 / Knowledge」）を `nav.ts` に追加し、`quizzes` と `learning` を 1 項目（または親 1・子 2）に再編する。
- [ ] 統合画面の構成: 理解負債のある領域（ギャラクシーの black_hole / dim_star、知識負債）を起点に、各領域から「学習（input: 資料を読む）」と「クイズ（output: 解いて KC を上げる）」へ分岐する導線にする。
- [ ] ルート再編: `quizzes/*` と `learning/*` を統合セクション配下に寄せる（パス変更時は既存ディープリンク `plan_learning.deepLink` / クイズ結果→学習プラン生成の導線 `result→/learning?from=quiz` を更新）。
- [ ] クイズ↔学習の相互リンクを整える（現状は学習→クイズの逆リンクが無い）。
- [ ] nav pill（クイズ受験可能数・KC%）の表示を統合セクションに合わせて再配置する。

### C. 全体
- [ ] パンくず・アクティブ判定・i18n ラベルを新 IA に合わせて更新する。
- [ ] [049] の自動リフレッシュ配線を、エージェント廃止後の「ダッシュボード状況カード」と統合セクションにも適用する。

## 完了条件
- ナビから独立した「エージェント」項目が無くなり、解析/ループ状況は観測台で確認できる。
- 「学習」と「クイズ」が 1 セクションに統合され、理解負債領域から input（学習）/ output（クイズ）へ自然に分岐できる。
- 旧ルートへのディープリンク（コックピットの各 deepLink、クイズ結果→学習）が新 IA でも切れずに動く。
- パンくず／アクティブ表示／i18n が新構成と整合する。

## 技術詳細
- 現ナビ: `frontend/src/lib/config/nav.ts:49-128`（`understand`: overview/galaxy/matrix/quizzes/agents/learning、`reference`: repos、`system`: settings）。
- エージェント: ルート `frontend/src/routes/[org]/[project]/agents/+page.svelte`、`frontend/src/lib/components/agents/*`（profile-header / narrative-stream / agent-pipeline / pipeline-node 等）、`frontend/src/lib/stores/agent-store.svelte.ts`。
- 学習: `frontend/src/routes/[org]/[project]/learning/*`、`frontend/src/lib/components/learning/*`（plan-progress / resource-list / resource-card）。
- クイズ: `frontend/src/routes/[org]/[project]/quizzes/*`（list / `[sessionId]` / `[sessionId]/result`）、`frontend/src/lib/components/quiz/*`、`frontend/src/lib/stores/quiz-store.svelte.ts`。
- 既存導線: コックピットの deepLink（`analysis-run-store.svelte.ts`: `loop_agents→/agents`、`plan_learning→/learning?planId`）、クイズ結果→学習プラン生成（`quizzes/[sessionId]/result/+page.svelte` → `/learning?from=quiz&attemptId=...`）。

## 参考
- 関連: [011 Twin Agent 活動ビュー](./011-agents-narrative-activity-stream.md)、[010 クイズ返済体験](./010-quiz-repayment-experience.md)、[012 学習プラン](./012-learning-plan-team-assets.md)、[020 IA/ナビ整備](./020-frontend-ia-nav-and-demo-honesty.md)、[049 解析結果の自動リフレッシュ](./049-frontend-analysis-run-refresh-wiring.md)
- 想定ラベル: `feature`, `frontend`
