# 解析ラン完了時に各画面を自動リフレッシュする配線を追加する

## 概要
解析ラン（コアループ）のコックピットから解析を実行しても、**クイズ・学習・エージェント（およびギャラクシー・観測台・マトリクス）の画面が更新されない**。各ページはマウント時に一度だけデータを取得し、解析ステージの完了（`analysisRun.stages.* === "COMPLETED"`）を監視して再取得する仕組みが無いため、生成済みデータが画面に反映されない。

## 背景・目的
コアループ（診断→返済→検証）の体験は「解析を回すと各画面に結果が現れる」ことが前提。現状は手動リロードや再ナビゲーションが必要で、解析を実行しても何も起きないように見える。各画面が**該当ステージ完了時に自動で再取得**するようにして、ループを成立させる。

## タスク
- [ ] 共通パターンの確立: 各ページ/ストアで `analysisRun.stages[stage].status === "COMPLETED"` を監視する `$effect` を追加し、完了時に再取得する（多重発火を避けるため「直近に処理した完了時刻/ステータス」をガード）。
- [ ] **マトリクス**: `detect_code` / `detect_knowledge` 完了で `listDebts()` を再取得（`matrix/+page.svelte:33-46` の効果に完了監視を追加）。
- [ ] **ギャラクシー**: `analyze_galaxy` 完了で `galaxy.load()` を再取得（`galaxy/+page.svelte:22`、`galaxy-store` に再取得導線）。
- [ ] **クイズ**: `loop_agents`/生成完了で `quiz.loadAvailable()` を再取得し、nav pill（`quiz.availableCount`）も更新（`quizzes/+page.svelte`、`quiz-store`）。
- [ ] **学習**: 既存の「新規生成時の自動遷移」（`learning/+page.svelte:24-38`）に加え、既存プランも完了時に再取得（`learning/+page.ts` の一度きりロードを是正）。
- [ ] **観測台**: いずれかのステージ完了で `getOverview()` を再取得（`+page.svelte:41-55`）。
- [ ] **エージェント**: `loop_agents` 完了で `agents.load()` を再取得（`agents/+page.svelte:18-20`、`agent-store`）。※ ナビ再編（051）でエージェントビューを廃止する場合は、ダッシュボードの「解析/ループ状況カード」側に同等の再取得を適用する。
- [ ] ストア（`quiz` / `galaxy` / `agent`）に冪等な再取得メソッドを用意し、`invalidateAll()` 乱用ではなくストア更新で反映する。

## 完了条件
- コックピットから解析を実行すると、各ステージ完了に応じて**対応画面が手動操作なしで最新データに更新**される。
- 再取得の多重発火・無限ループが無い（ガードが効いている）。
- プロジェクト切替時に解析ランの監視状態が適切にリセットされる（[044] と整合）。

## 技術詳細
- 解析ランストア: `frontend/src/lib/stores/analysis-run-store.svelte.ts`（5 ステージ `detect_code`/`detect_knowledge`/`analyze_galaxy`/`plan_learning`/`loop_agents`、1.5s ポーリング、`COMPLETED`/`FAILED`、各 `deepLink`）。
- コックピット: `frontend/src/lib/components/overview/analysis-run-cockpit.svelte`。
- 一度きりロードの該当箇所:
  - クイズ `quizzes/+page.svelte:20`（手動 `loadAvailable`）/ `quiz-store.svelte.ts`（監視なし）
  - 学習 `learning/+page.svelte:24-38`（新規生成のみ）/ `learning/+page.ts:16-24`
  - エージェント `agents/+page.svelte:18-20` / `agent-store.svelte.ts`
  - ギャラクシー `galaxy/+page.svelte:22` / `galaxy-store.svelte.ts`
  - 観測台 `+page.svelte:41-55` / マトリクス `matrix/+page.svelte:33-46`
- 解決パターン例:
  ```ts
  $effect(() => {
    if (analysisRun.stages.detect_code.status === "COMPLETED") void loadDebts();
  });
  ```

## 参考
- 関連: [037 生成トリガー導線と解析ラン・コックピット](./037-frontend-generation-triggers-and-analysis-run-cockpit.md)、[044 analysis-run ストアのライフサイクル](./044-frontend-analysis-run-store-lifecycle.md)、[019 コアループのディープリンク配線](./019-frontend-core-loop-deep-linking.md)
- 想定ラベル: `bug`, `frontend`
