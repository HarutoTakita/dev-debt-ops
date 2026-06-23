# 生成トリガーを「解析」ボタンに集約する（学習プラン・クイズも解析で全生成、メニューは表示専用）

## 概要

現状、コンテンツ生成のトリガーが**各メニューページに散在**している（学習ページの「プラン生成」、単元リストの「プラン作成 / 確認クイズを用意」、クイズの個別生成、matrix/repos の検知、galaxy の分析）。ユーザーにとって「どこで何を生成するのか」が分かりにくい。

本 issue は、**生成トリガーを Overview のコックピットの「解析」ボタン（`analysisRun.runAll`）1 つに集約**する。「解析」を押せば、コード負債・知識負債・KC・機能クラスタリングに加えて、**機能ごとの学習プランと確認（ベースライン）クイズまで全て生成**される。各メニューページは**表示専用**にし、未生成時は空状態で「『解析』を実行してください」へ誘導する。

> 製品判断（オーナー確定）: 生成導線は「解析」1 本に集約。メニューでの個別生成は廃止。学習プランは**機能ごとに全機能分**生成（プロジェクト全体 1 本ではなく、単元モデル issue 063 に整合）。

## 背景・目的

### 現状（生成トリガーが分散）

- 解析ラン `runAll`（`frontend/src/lib/stores/analysis-run-store.svelte.ts`）のステージは **5 つ**：`detect_code` / `detect_knowledge` / `analyze_galaxy` / `cluster_features` / `plan_learning`。
  - `plan_learning` は `generatePlan(org, project, {})` で**プロジェクト全体 1 本**の学習プランを生成。
  - **クイズは解析に含まれない**。
- メニュー側の生成トリガー（撤去対象）:
  - `routes/[org]/[project]/matrix/+page.svelte` / `repos/+page.svelte` … `runStage("detect_code")` ボタン
  - `components/galaxy/coming-soon-placeholder.svelte` … `runStage("analyze_galaxy")`
  - `routes/[org]/[project]/learning/+page.svelte` … `generatePlanNow`（`runStage("plan_learning")`）
  - `components/learning/knowledge-unit-list.svelte` … `generatePlan({featureId})` / `generateBaselineQuizzes`（単元ごと）
  - クイズ受験ページ群 … `generateQuiz(filePath)` の個別生成
- 既存バックエンド資産（再利用可）:
  - `POST .../baseline-quizzes`（`quizzes.py`、issue 054 実装済み）= **機能ごと・呼び出し本人分・冪等**にベースラインクイズセッションを作成し生成を enqueue。`{created}` を返す（単一 job ではなく N 件ファンアウト）。
  - `POST .../learning/plans`（`generatePlan`）= 学習プラン 1 本を生成（`feature_id` 任意）。**全機能分を一括生成する経路は無い**（本 issue で追加）。

### 目的

1. 「解析」(`runAll`) を**唯一の生成トリガー**にし、学習プラン（機能ごと全機能分）と確認クイズ（機能ごとベースライン）も生成する。
2. 各メニューページの生成ボタンを撤去し、**表示専用**＋空状態（「解析を実行」誘導）にする。
3. コックピットに新ステージ（学習・クイズ）を表示し、進捗が 1 画面で追える。

### 前提・連動 issue

- **052**（features/feature_files）/ **054**（baseline-quizzes、実装済み）/ **055**（機能 KC ロールアップ）/ **063**（単元 = 機能の learn→confirm）。本 issue は 063 の「単元ごとに学習＋確認クイズ」を**解析時に一括生成**する形に落とす。
- **037**（解析ラン・コックピット）= `analysis-run-store` / `analysis-run-cockpit` の所有。本 issue はステージ集合を拡張する。

## 設計

### A. バックエンド — 機能ごと学習プランの一括生成エンドポイント（新規）

`baseline-quizzes` と対称の「全機能分の学習プランを生成」エンドポイントを追加する。

- `POST /api/v1/orgs/{slug}/projects/{project_slug}/baseline-plans`（または `learning/plans:generate-all`）→ `202 { created }`。
- 最新 `feature_clustering` run の全 `features` を対象に、`learning_plans.feature_id` 単位でプランを生成 enqueue（`learning_plan_generation`）。
- **冪等**: 既に当該機能のプランがあればスキップ（`baseline-quizzes` の冪等規約に倣う）。`OrgScope` 認可・方式 B・snake_case。
- `gap_concepts` は当該機能の低 KC ファイル/概念から導出（054 の機能展開・055 ロールアップと整合）。

### B. フロント store — `runAll` に「学習」「クイズ」ステージを追加

`STAGES`（`analysis-run-store.svelte.ts`）に 2 ステージを追加し、`cluster_features` / `analyze_galaxy` の後に実行する：

| stage id | jobType / API | dependsOn | 備考 |
|---|---|---|---|
| `plan_learning`（変更） | `baseline-plans`（A の新 API） | `cluster_features` | 全機能分の学習プラン生成に変更（`generatePlan({})` 単発をやめる） |
| `confirm_quizzes`（新規） | `baseline-quizzes`（054） | `cluster_features` | 機能ごとベースラインクイズ生成 |

- 両 API は**単一 job を返さない**（N 件ファンアウト + `{created}`）。store を「**job ポーリング不要のステージ**」に対応させる：`enqueue` が job_id を返さない場合、enqueue 成功（202）で `COMPLETED` とする（個々の生成は背景で進み、クイズ/学習ページ側が `status` を表示）。`#poll` は job_id 必須のため、`runStage` で job_id 不在時に `COMPLETED` をセットする小改修。
- `dependsOn` を実際に機能させる（現状は全ステージ `[]`）。クイズ/学習は `cluster_features` 完了が前提なので依存を張り、失敗時はスキップ。
- `runAll` の順序: `detect_code` → `detect_knowledge` → `analyze_galaxy` → `cluster_features` → `plan_learning` → `confirm_quizzes`。

### C. フロント — メニューページを表示専用化

各ページの**生成ボタンを撤去**し、未生成時は共通の空状態（「『解析』を実行してください」＋ Overview/コックピットへの導線）にする：

- `matrix/+page.svelte` / `repos/+page.svelte`: `detect_code` ボタン撤去。
- `galaxy/coming-soon-placeholder.svelte`: `analyze_galaxy` ボタン撤去。
- `learning/+page.svelte`: `generatePlanNow` ボタン撤去（クイズ結果経由の `+page.ts` 自動生成も見直し）。
- `knowledge-unit-list.svelte`: 単元ごとの「プラン作成 / 確認クイズを用意」ボタン撤去 → 生成済みを表示、未生成は空状態。
- クイズ受験ページ: 個別 `generateQuiz` トリガー撤去（クイズは解析由来のセッションを受験する導線のみ）。
- 空状態文言・コックピットのステージラベル（学習・クイズ）を i18n（ja/en）に追加。

> 受験/学習の**実行**（クイズを解く・資料を開く・読了トグル・採点）は従来どおりメニューで行う。撤去するのは**生成（コンテンツを作る）トリガー**のみ。

## タスク

### backend
- [ ] `baseline-plans`（全機能分の学習プラン生成）エンドポイントを追加（`baseline-quizzes` を雛形・冪等・`202 {created}`）。`router` 登録、Annotated DI 順序厳守。
- [ ] test（api）: 全機能分のプランが生成 enqueue され、既存プランはスキップ（冪等）。認可。

### frontend
- [ ] `analysis-run-store.svelte.ts`: `plan_learning` を `baseline-plans` 呼び出しへ変更、`confirm_quizzes` ステージ追加、job 不在ステージの即 COMPLETED 対応、`dependsOn` 有効化、`runAll` 順序更新、`ALL_STAGE_IDS`/`StageId` 更新。
- [ ] `client.ts`: `generateBaselinePlans`（新 API）追加。
- [ ] `analysis-run-cockpit.svelte`: 新ステージ表示。
- [ ] メニューページの生成ボタン撤去 + 空状態（matrix / repos / galaxy / learning / knowledge-unit-list / quizzes）。
- [ ] i18n（ja/en）: 空状態・ステージラベル。
- [ ] test（vitest）: `runAll` が学習・クイズステージまで回ること、job 不在ステージが COMPLETED になること、メニューに生成ボタンが無いこと。

## 完了条件
- Overview の「解析」ボタン 1 つで、検知・KC・機能クラスタリング・**機能ごと学習プラン**・**機能ごと確認クイズ**まで生成される。
- 各メニューページに生成ボタンが無く、未生成時は「解析を実行」へ誘導、生成済みは表示・受験/学習ができる。
- 解析の再実行は冪等（既存の機能プラン/ベースラインクイズはスキップ）。
- フロント: `bun run check`（警告ゼロ）/ `lint` / `test:unit`、バックエンド: ruff/ty/pytest が通る。
- `CHANGELOG.md`（日本語）に `Changed`（生成トリガーを解析に集約）/ `Added`（baseline-plans）を追記。

## 対象外・保留
- 受験/学習の**実行 UI** 自体の再設計（063 の単元ハブ）。本 issue は生成トリガーの集約に限定。
- 受験対象メンバーの拡張（現状 baseline は呼び出し本人分のみ、054 の方針踏襲）。
- コード負債の粒度集計（060）/ クラス・関数粒度（061）。

## 参考
- `frontend/src/lib/stores/analysis-run-store.svelte.ts`（`STAGES` / `runAll` / `runStage` / `#poll`）、
  `frontend/src/lib/components/overview/analysis-run-cockpit.svelte`（`runAll` ボタン）、
  `frontend/src/lib/api/client.ts`（`generatePlan` / `generateBaselineQuizzes` / `clusterFeatures`）、
  `backend/api/app/api/v1/quizzes.py`（`baseline-quizzes` 雛形）、`backend/api/app/api/v1/learning.py`（`generatePlan`）。
- 連動 issue: [052](./052-backend-measurement-granularity-and-feature-model.md) / [054](./054-backend-initial-feature-baseline-quiz.md) / [055](./055-backend-feature-granularity-debt-aggregation-api.md) / [063](./063-knowledge-unit-learn-confirm-loop.md) / [037](./037-frontend-generation-triggers-and-analysis-run-cockpit.md)。
- 規約: `CLAUDE.md`（Svelte 5 runes・shadcn `ui/` 読取専用・Annotated DI 順序・方式 B・snake_case 配信・i18n ja/en・CHANGELOG 日本語・ゲート）。
