# サイドバー各機能の「生成」を起動する UI — 解析ランのコックピットと生成導線を配線する

## 概要

サイドバー（`understand` セクション）には **Overview / Galaxy / Matrix / Quizzes / Agents / Learning** が並び、
それぞれの裏側 API（enqueue + `GET /jobs/{id}` ポーリング）は `frontend/src/lib/api/client.ts` に
**配線済み**（`analyzeStack` / `detectDebts` / `detectKnowledgeDebts` / `analyzeGalaxy` / `generateQuiz` /
`createRepaymentPr` / `submitQuiz` 等）であるにもかかわらず、**これらを起動する UI が存在しない**。
結果として、ユーザーは「実際の処理（解析・生成）を走らせる」入口を持たず、各 Map はモック表示か
Coming Soon プレースホルダのまま止まっている。

本 issue は、この「生成を起動する UI 層」を新設する。中核は **プロジェクトトップ（Overview）を
『解析ラン・コックピット』にする**ことであり、単一の主アクション「このリポジトリを解析する」から
**ツインエージェントのコアループ（検知 → 分析 → 計画 → 返済 → 検証）を段階生成として可視化**し、
各ステージのデータが揃うたびに対応する Map（Matrix / Galaxy / Quizzes / Learning）へ deep-link する。
併せて各 Map のサブページにも、empty / stale 状態からの **生成・再生成 CTA** を置き、すべてが
**1 つの共有ラン状態（`analysis-run-store`）** を参照するようにする。

**フロント中心**（既存の enqueue 関数を起動・束ねる UI と状態管理が主眼）。新規バックエンド処理は
作らないが、学習プラン生成（035）・エージェントループ起動（036）の client 関数が未配線なら追加する
（後述「対象外・保留」参照）。

## 背景・目的

### 横断テーマ — 「処理はあるが起動できない」

このプロダクトは **Tech Debt Twin Agent**（技術的負債を解析してマップ化し、返済まで導く
自律エージェント）であり、その価値は「リポジトリを渡すと、ツインがコードと知識の負債を検知し、
ギャラクシー / マトリクスに可視化し、クイズと PR で返済させ、学習プランで検証する」という
**一連のループ**にある。バックエンドは issue 015〜036 でこのループを非同期パイプライン
（Cloud Tasks enqueue + `Job` ポーリング、issue 016 / 018 のパターン）として実装中で、
フロントの API クライアントも各 enqueue 関数を持つ。

しかし **「ループを起動する操作」がどこにも露出していない**。具体的な現状：

- **生成 API は client にあるが呼び出し元が無い。** `frontend/src/lib/api/client.ts:259-450` に
  `analyzeStack`（018）/ `detectDebts`（028）/ `detectKnowledgeDebts`（030）/ `analyzeGalaxy`（032）/
  `generateQuiz`（034）/ `submitQuiz`（034）/ `createRepaymentPr`（033）が定義済み。だが
  これらを起動する Button / フローを持つコンポーネントは（stack 解析の `tech-stack-panel` を除き）存在しない。
- **サイドバー項目の多くが `comingSoon: true`。** `frontend/src/lib/config/nav.ts:62,83,88,99,124` で
  Galaxy / Quizzes / Agents / Learning / Settings が Coming Soon 扱い。各サブページは
  プレースホルダ（`coming-soon-placeholder.svelte`）か mock 描画で、生成の入口を持たない。
- **「最初の 30 秒」の主アクションが無い。** issue 022 は Overview に getting-started カードと
  スキャンライフサイクル（「スキャン開始」CTA）を入れるが、それは **stack 解析単体**の話で、
  「ループ全体を起動して各 Map を満たす」コックピットにはなっていない。
- **状態が画面ごとにバラバラ。** 各ストア（`galaxy-store` / `quiz-store` / `agent-store`）は
  `loadMock()` 等を個別に持つだけで、「いま何が生成済みか / 生成中か / 失敗か」を横断把握する
  単一の真実源が無い。

### 目的

1. **単一の主アクションでコアループを起動する。** プロジェクトトップ（Overview）に
   「このリポジトリを解析する」primary CTA を置き、押下で **段階生成**（検知 → 分析 → 計画 → 返済 → 検証）を
   開始する。各ステージは enqueue + ポーリングで進み、完了するたびに対応 Map のデータが利用可能になる。
2. **進捗とナビゲーションを可視化する。** ステージごとに状態（待機 / キュー / 処理中 / 完了 / 失敗）と
   `agent_trace` の最新行を表示し、完了ステージから対応 Map（Matrix / Galaxy / Quizzes / Learning）へ
   deep-link する。「いま何が起きていて、次にどこを見ればよいか」を常に提示する。
3. **各サブページにも生成導線を置く。** Galaxy / Matrix / Quizzes / Learning の empty / stale 状態に
   「生成する / 再生成する」CTA を配置し、ページ直行ユーザーも行き止まりにしない。
   ただし状態は **コックピットと共有**し、二重起動・状態不整合を防ぐ。
4. **1 つの共有ラン状態を持つ。** `analysis-run-store`（Svelte 5 クラスベース runes）が
   各パイプラインの enqueue + ポーリング + ステージ依存（DAG/順序）を所有し、コックピットと
   各サブページ・サイドバー pill が同じ状態を参照する。
5. **偽データを本物に見せない（issue 022 の方針を継承）。** 生成前は「未解析」、生成中は中間状態、
   完了後に実データ、を明示する。実 API 未整備の段階では mock を「Sample/デモデータ」バッジ付きで使う。

### 前提 Issue（depends_on / 連携）

- **016** `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks enqueue + `Job` ライフサイクル +
  `GET /api/v1/jobs/{id}` ポーリング。本 issue の全 enqueue/ポーリングの土台。`JobStatus` は大文字
  （`QUEUED`/`PROCESSING`/`COMPLETED`/`FAILED`/`CANCELLED`）。
- **018** `docs/issue/018-stack-analysis-async-job-on-service.md` — enqueue → `getJob` ポーリングの
  **フロント実装パターンの原型**（`stack-analysis-store.svelte.ts` の `analyze()` / `#poll()` / `state` 遷移）。
  本 issue の `analysis-run-store` はこのパターンを各パイプラインへ一般化したもの。
- **028 / 029 / 030** — コード負債検知 / KC 算出 / 知識負債検知パイプライン（`detectDebts` /
  `detectKnowledgeDebts` 等の起動先）。
- **031** `docs/issue/031-backend-overview-and-debt-registry-api.md` — Overview 集計 / 負債レジストリ配信。
  **検知結果が無いときの 404 / 空配列**の挙動はここで定義 → コックピットの「未解析」表現の根拠。
- **032** — Galaxy 個人 KC 配信 + `analyze-galaxy` enqueue。
- **033** — 返済 PR 生成（`createRepaymentPr`、**負債単位**のアクション）。
- **034** — クイズ生成 / 採点（`generateQuiz` は**ファイル単位**、`submitQuiz` は採点）。
- **035** `docs/issue/035-backend-learning-plan-generation-and-api.md` — 学習プラン生成 + 配信。
- **036** `docs/issue/036-backend-agents-autonomous-loop-and-narrative.md` — **検知 → 分析 → 計画 → 返済 → 検証の
  5 ステージ自律ループを束ねるオーケストレーション層**。本 issue のコックピットが起動する「ループ全体」は
  この 036 のオーケストレーションに対応する（Agents ページは同じループの一人称ナラティブ表示）。

> 多くの enqueue 関数は client に配線済みのため、本 issue の主作業は **UI と状態管理**である。
> 実 API が未完の段階では、各ストアの `loadMock()` 経路を「Sample バッジ付き」で温存し、
> `import.meta.env` や設定フラグで実 API / mock を切替可能にする（issue 022 のライフサイクル方針に整合）。

### 独自性（既存 issue との差分）

- **022 との差分:** 022 は Overview の getting-started カード + **stack 解析単体**のスキャンライフサイクル
  （「Sample バッジ」「スキャン開始 CTA」）まで。本 issue は **ループ全体（複数パイプライン）の起動と
  段階可視化・横断状態管理**を担う。022 のスキャン中間状態コンポーネント・localStorage 永続パターンは流用するが、
  対象を「stack だけ」から「検知〜検証の全ステージ」へ拡張する。
- **019 との差分:** 019 は既存ノード間の **遷移（deep-link）配線**（静的表示のクリック先を実装）。本 issue は
  「**生成を起動**して、生成済みステージから Map へ送る」起点側を作る。019 の deep-link 先（`/matrix?cell=...` 等）を
  コックピットの「完了ステージ → Map」リンクの行き先として再利用する。
- **036 との差分:** 036 は **バックエンドのオーケストレーション + ナラティブ配信 API**。本 issue は
  そのループを **起動する操作 UI とコックピット表示**。Agents ページ（036 のフロント）はループの
  「物語ビュー」、Overview コックピットは「コントロール + 結果の入口」という役割分担にする。

## 設計判断 — 4 つの案の比較と採用案

提示された 4 案を比較し、**案 2（プロジェクトトップで順次生成 + ナビゲート）を中核に、
案 3（トップの一発起動）を「段階可視化付き」で取り込むハイブリッド**を採用する。

| 案 | 内容 | 評価 |
|---|---|---|
| 1. 各サブページに個別生成ボタン | Galaxy / Matrix / Quiz 各ページに生成ボタンを置くだけ | ❌ 中核には不採用。入口が分散し「初見で何からやるか」が見えない。各ページが行き止まり。**ただし empty/stale の再生成 CTA としては併用**（目的 3） |
| 2. トップページで順次生成 + ナビゲート | プロジェクトトップを起点に、段階的に生成しながら各 Map へ誘導 | ⭕ **採用（中核）**。コアループ＝プロダクトの主張そのものを 1 画面で体験させられる |
| 3. トップの「解析」一発で matrix/galaxy/quiz を全生成 | ボタン 1 つで全部生成 | △ 「一発起動」は採用。ただし**サイレントに全生成ではなく段階を可視化**して各 Map に deep-link。理由: ①失敗を局所化できる ②長い待ち時間に進捗の物語を見せられる ③「何が生成されたか」が誠実に伝わる |
| 4. エージェントメニューに各機能の生成ボタン | Agents ページに生成ボタンを集約 | △ 操作の主にはしない。Agents は **036 の一人称ナラティブ（ライブ表示）に専念**。コックピットからループを起動し、Agents で「ツインが今やっていること」を観る分業。Agents からも run を起動できる**二次導線**は可 |

### 採用案：解析ラン・コックピット（Analysis Run Cockpit）

```
プロジェクトトップ /[org]/[project]（Overview）
┌──────────────────────────────────────────────────────────────┐
│  [ このリポジトリを解析する ]  ← 単一の主 CTA（未解析時の primary action） │
│                                                              │
│  ── 解析ラン（コアループ）─────────────────────────────────────  │
│   ① 検知   stack解析 + コード/知識負債検知    ●完了 → [Matrix を見る]  │
│   ② 分析   KC 算出 / ギャラクシー生成         ◐処理中 "星を配置中…"     │
│   ③ 計画   学習プラン生成                     ○待機               │
│   ④ 返済   クイズ生成                         ○待機 → [Quiz へ]      │
│   ⑤ 検証   学習プラン検証 / 進捗集計           ○待機               │
│  ───────────────────────────────────────────────────────────  │
│  （完了後）OverviewDashboard（実データ） + getting-started(022)        │
└──────────────────────────────────────────────────────────────┘
   各サブページ: 未生成なら「生成する」/ 既存なら「再生成」CTA（同じ run 状態を共有）
   Agents ページ: 同じループの一人称ナラティブ（036）。「ループを実行」二次導線も可
```

- 各ステージは `Job` ベース。状態は **待機 / キュー / 処理中 / 完了 / 失敗** の 5 値（`JobStatus` 大文字に対応）。
- ステージ間には**依存**がある（例: クイズ生成は負債検知 / KC 完了後）。`analysis-run-store` が
  順序（または DAG）を持ち、前段完了で次段を自動 enqueue する「順次生成」を既定にする。
  「全部まとめて」押下時もこの順序で段階的に走らせ、各完了で deep-link を活性化する。
- 「ステージ単体の再生成」も可能にし、目的 3 の各サブページ CTA はこの単体 enqueue を呼ぶ。

## タスク

### A. 共有ラン状態 `analysis-run-store`（新設）

- [ ] `frontend/src/lib/stores/analysis-run-store.svelte.ts` を新設する（Svelte 5 クラスベース runes・kebab-case）。
      018 の `stack-analysis-store.svelte.ts`（`analyze()` / `#poll()` / `state` 遷移）を**各パイプラインへ一般化**する。
- [ ] ステージ定義を持つ。各ステージ = `{ id, label(), enqueue, jobId, status, deepLink(ctx), dependsOn[] }`。
      初期ステージ集合（コアループ）:

  | ステージ | 起動する client 関数 | 完了後の deep-link |
  |---|---|---|
  | ① 検知（stack） | `analyzeStack(owner, repo)`（018） | Repos / Overview |
  | ① 検知（コード負債） | `detectDebts(org, project)`（028） | `/matrix` |
  | ① 検知（知識負債） | `detectKnowledgeDebts(org, project)`（030） | `/matrix?kind=...`（019 の入口） |
  | ② 分析（ギャラクシー/KC） | `analyzeGalaxy(org, project)`（032 / 029） | `/galaxy` |
  | ④ 返済（クイズ） | `generateQuiz(org, project, filePath)`（034、対象ファイルは検知結果から選定） | `/quizzes` |
  | ③ 計画 / ⑤ 検証（学習プラン） | `generateLearningPlan(org, project)`（035・**client 追加要**） | `/learning` |
  | （任意）ループ全体 | `runAgentLoop(org, project)`（036・**client 追加要**） | `/agents` |

- [ ] 各ステージは enqueue → `jobId` 保存 → `getJob(jobId)` を間隔ポーリング（018 と同じ 1.5s 目安、
      指数バックオフ可）。`job.status === "COMPLETED"` で完了・次段 enqueue、`"FAILED"` でそのステージのみ失敗表示
      （他ステージは継続）。`agent_trace` の最新行を `currentStep` として公開。
- [ ] `runAll()`（依存順に全ステージを順次起動）/ `runStage(id)`（単体起動・再生成）/ `cancel()`（全ポーリング停止）。
      ポーリング `setTimeout` のクリーンアップ（コンポーネント破棄・`cancel()` 時）を必ず行う（リーク防止）。
- [ ] 冪等・多重起動防止: 既に `QUEUED`/`PROCESSING` のステージは再 enqueue しない。完了済みステージの
      再生成は明示操作（再生成ボタン）でのみ。
- [ ] mock フォールバック: 実 API が未整備のステージは、対応ストアの `loadMock()` を「Sample」状態として
      使えるよう切替フラグを持つ（issue 022 のライフサイクル方針。本番ビルドで dev 文言を出さない）。

### B. コックピット UI（Overview トップ）

- [ ] `frontend/src/lib/components/overview/analysis-run-cockpit.svelte` を新設する（kebab-case・runes）。
      未解析時に主 CTA「このリポジトリを解析する」、解析中/解析済みにステージリスト（状態 + `currentStep` +
      完了ステージの deep-link）を表示する。
- [ ] `frontend/src/routes/[org]/[project]/+page.svelte` の Overview 上部に差し込む。
      issue 022 の getting-started カード / スキャン中間状態と**役割を整理して共存**させる
      （getting-started = 静的な道案内、cockpit = 実行中の動的状態）。022 が先行実装済みなら、
      `repo.connected ? overviewMock : null`（`+page.svelte:17`）の分岐を「ラン状態」基準に置き換える。
- [ ] 完了後は従来の `OverviewDashboard`（`frontend/src/lib/components/overview/overview-dashboard.svelte`）に合流。
      モック由来の間は 022 の「Sample/デモデータ」バッジを継承表示。
- [ ] ステージ進捗の視覚表現は shadcn-svelte プリミティブ（`progress` 未導入なら
      `bunx shadcn-svelte@latest add progress`）または Tailwind v4 アニメーション。`ui/` 配下は読み取り専用、
      ラッパーは `ui/` 外で合成（CLAUDE.md 規約）。

### C. 各サブページの生成・再生成 CTA（empty / stale 状態）

各ページの Coming Soon / empty 状態に、`analysis-run-store` の該当ステージを起動する CTA を置く
（状態は store と共有。生成中はボタンを進捗表示に切替）。

- [ ] **Galaxy** `frontend/src/routes/[org]/[project]/galaxy/+page.svelte` + 
      `frontend/src/lib/components/galaxy/coming-soon-placeholder.svelte`。既存の `startScan()` /
      `galaxy.loadMock()`（022 で primary/secondary 化予定）を `runStage("galaxy")` に接続。
- [ ] **Matrix** `frontend/src/routes/[org]/[project]/matrix/+page.svelte`。検知結果が無いとき
      （031 の空配列 / 404）に「負債を検知する」CTA → `runStage("detect-debts")`。
- [ ] **Quizzes** `frontend/src/routes/[org]/[project]/quizzes/+page.svelte` +
      `frontend/src/lib/components/quiz/coming-soon-placeholder.svelte`。`quiz.loadAvailable()` の
      dev リンク（022 で「デモを見る」化）と並べて「クイズを生成する」CTA → `runStage("quiz")`。
- [ ] **Learning** `frontend/src/routes/[org]/[project]/learning/+page.svelte`。「学習プランを生成する」
      CTA → `runStage("learning")`。
- [ ] **Agents** `frontend/src/routes/[org]/[project]/agents/+page.svelte`。一次は 036 のナラティブ表示。
      「ループを実行する」**二次導線**として `runAll()`（または `runAgentLoop`）を置き、起動後はナラティブへ。
- [ ] サイドバー pill（`frontend/src/lib/config/nav.ts` の `galaxy.myKc` / `MOCK_DEBTS.length` /
      `quiz.availableCount`）を、可能な範囲で `analysis-run-store` の完了状態に追随させる
      （生成前は pill 非表示、完了後に実数）。

### D. client / schema の補完（不足分のみ）

- [ ] **学習プラン生成（035）** の client 関数が無ければ追加: `generateLearningPlan(org, project)` →
      `202 {job_id}`（`analyzeStackJobSchema` 互換）。`frontend/src/lib/api/client.ts`。
- [ ] **エージェントループ起動（036）** の client 関数が無ければ追加: `runAgentLoop(org, project)` →
      `202 {job_id}`。ループ進捗は 036 の `getPipeline` 再取得 or `getJob` ポーリング。
- [ ] `frontend/src/lib/api/schemas.ts` に不足スキーマがあれば Zod v4 で追加（snake_case 保持・大文字 `JobStatus`）。
- [ ] クイズ生成の対象ファイル選定（`generateQuiz` は `file_path` 必須）: 検知済み負債/KC ギャップの
      上位ファイルを既定対象にするヘルパを置く（コックピットの「返済」ステージが自動選定）。

### E. 多言語化・誠実表示

- [ ] Paraglide 2.0 で文言を追加（`frontend/messages/ja.json` 主・`en.json` 従、再生成）。
      例: `analysis_run_cta`（このリポジトリを解析する / Analyze this repository）、
      `analysis_stage_detect`/`_analyze`/`_plan`/`_repay`/`_verify`、`analysis_stage_queued`/`_processing`/`_done`/`_failed`、
      `analysis_view_matrix`/`_galaxy`/`_quizzes`/`_learning`、`analysis_regenerate`（再生成する）等。
- [ ] 本番ビルドで dev 文言・dev 導線を出さない（022 と同じ規約）。mock 使用時は「Sample/デモデータ」を明示。

### F. テスト

- [ ] `analysis-run-store` のユニットテスト（`.spec.ts`、node）: `runAll` の依存順起動、`runStage` 単体、
      `COMPLETED`/`FAILED` 遷移、多重起動防止、`cancel()` のタイマークリーンアップ（API モック）。
- [ ] `analysis-run-cockpit.svelte.spec.ts`（browser-mode）: 未解析→CTA表示、起動→ステージ進捗、
      完了→deep-link 活性化、失敗ステージの局所表示。
- [ ] 各サブページ CTA の最小テスト（生成中はボタンが進捗表示に切替、store 状態を共有）。

## 完了条件

- プロジェクトトップ（Overview）に「このリポジトリを解析する」主 CTA があり、押下で
  **コアループ（検知 → 分析 → 計画 → 返済 → 検証）が段階生成**として開始されること。
- 各ステージの状態（待機 / キュー / 処理中 / 完了 / 失敗）と進捗（`agent_trace` 最新行）が表示され、
  **完了したステージから対応 Map（Matrix / Galaxy / Quizzes / Learning）へ deep-link** できること。
- いずれかのステージが失敗しても**他ステージは継続**し、失敗は局所的に表示・再実行できること。
- Galaxy / Matrix / Quizzes / Learning の各サブページに、empty / stale 状態からの生成・再生成 CTA があり、
  それらが **コックピットと同じ `analysis-run-store` の状態を共有**すること（二重起動しない）。
- Agents ページがループの一人称ナラティブ（036）を表示し、必要なら同ページからも run を起動できること。
- 生成前は「未解析」、生成中は中間状態、完了後に実データ（モック由来の間は「Sample」バッジ）という
  **誠実なライフサイクル**（022 継承）が保たれ、本番ビルドに dev 文言が出ないこと。
- 学習プラン生成（035）・エージェントループ起動（036）の client 関数が（未配線なら）追加され、
  全ステージが `202 {job_id}` + `getJob` ポーリングの統一パターンで動くこと。
- 追加・変更文言が ja（主）・en（従）双方に存在し、Paraglide 再生成済みであること。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通ること。

## 技術詳細

### `analysis-run-store` のステージ駆動（抜粋イメージ）

```typescript
// frontend/src/lib/stores/analysis-run-store.svelte.ts（抜粋・設計イメージ）
import { analyzeStack, detectDebts, detectKnowledgeDebts, analyzeGalaxy, generateQuiz, getJob } from "$lib/api/client";

type StageStatus = "idle" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";

interface Stage {
  id: string;
  label: () => string;
  enqueue: (ctx: RunContext) => Promise<{ job_id: string }>;
  dependsOn: string[];          // 前提ステージ id（順次/DAG）
  deepLink: (ctx: RunContext) => string | null;
}

class AnalysisRunStore {
  stages = $state<Record<string, { status: StageStatus; jobId: string | null; step: string }>>({});
  // runAll(): dependsOn を満たしたステージから順に enqueue。各 COMPLETED で次段を起動。
  // runStage(id): 単体起動（サブページの再生成 CTA から）。
  // #poll(id): getJob を間隔取得し status/agent_trace を反映、COMPLETED で deepLink を活性化。
  // cancel(): 全タイマー停止（コンポーネント破棄時に必ず呼ぶ）。
}
export const analysisRun = new AnalysisRunStore();
```

> ポーリング・状態遷移・タイマークリーンアップは 018 の `stack-analysis-store` を踏襲する。
> 「ステージ集合 + 依存順 + deep-link」を足したのが本 store の拡張点。

### ステージ ↔ バックエンド issue ↔ Map 対応

| ループ段階 | バックエンド issue | client 関数（現状） | 表示先 Map |
|---|---|---|---|
| 検知 | 018（stack）/ 028（コード負債）/ 030（知識負債） | `analyzeStack` / `detectDebts` / `detectKnowledgeDebts`（配線済） | Repos / Matrix |
| 分析 | 029（KC）/ 032（Galaxy） | `analyzeGalaxy`（配線済） | Galaxy |
| 計画 | 035（学習プラン） | `generateLearningPlan`（**追加要**） | Learning |
| 返済 | 033（PR・負債単位）/ 034（クイズ） | `createRepaymentPr` / `generateQuiz` / `submitQuiz`（配線済） | Matrix / Quizzes |
| 検証 | 035（プラン検証）/ 031（集計） | `getOverview` / `getLearningPlan`（読み取り） | Overview / Learning |
| ループ全体 | 036（オーケストレーション + ナラティブ） | `runAgentLoop`（**追加要**） | Agents |

### サイドバーとの整合

- `frontend/src/lib/config/nav.ts` の `comingSoon: true`（Galaxy/Quizzes/Agents/Learning）は、
  対応ステージが実 API で起動可能になった段階で順次外す（実 API 未整備の間は Coming Soon + 「デモを見る」を維持）。
- pill（`galaxy.myKc` / `MOCK_DEBTS.length` / `quiz.availableCount`）は `analysis-run-store` の完了状態に追随。
  生成前は非表示、完了後に実数を出す（偽の件数を見せない）。

## 対象外・保留

- **新規バックエンド処理・パイプラインの実装はしない。** 検知 / KC / 採点 / PR 生成 / 学習プラン / オーケストレーションの
  ロジックは 028〜036 が所有。本 issue は**それらを起動・束ねる UI と状態**に徹する。
- **client への関数追加は不足分のみ**（学習プラン 035・エージェントループ 036）。既存の enqueue 関数は流用する。
- **SSE / WebSocket は対象外。** ライブ更新はポーリング（`getJob` / 036 の `getPipeline` 再取得）。036 の MVP 方針に整合。
- **負債単位の返済 PR 生成（033）・ファイル単位のクイズ生成詳細（034）の個別 UX** は各 Map の詳細ページの責務で、
  本 issue は「コックピットからの一括/段階起動」と「empty 状態の生成 CTA」までを担う。
- **022 と実装が重なる箇所**（getting-started・スキャン中間状態・Sample バッジ）は 022 を先行・基盤とし、
  本 issue は cockpit としてその上に積む（重複実装を避け、022 のコンポーネント/localStorage 永続を流用）。

## 参考

- 関連 Issue（相互参照）
  - `docs/issue/016-async-task-queue-cloud-tasks.md` — Cloud Tasks enqueue + `Job` ポーリング基盤
  - `docs/issue/018-stack-analysis-async-job-on-service.md` — enqueue→`getJob` ポーリングのフロント原型（`stack-analysis-store`）
  - `docs/issue/019-frontend-core-loop-deep-linking.md` — コアループの deep-link 配線（cockpit の遷移先）
  - `docs/issue/022-frontend-onboarding-and-analysis-lifecycle.md` — getting-started / スキャンライフサイクル / Sample バッジ（基盤）
  - `docs/issue/031-backend-overview-and-debt-registry-api.md` — 検知結果ゼロ時の 404/空配列（「未解析」表現の根拠）
  - `docs/issue/036-backend-agents-autonomous-loop-and-narrative.md` — 5 ステージ自律ループのオーケストレーション + ナラティブ
- 関連ファイル（改修・流用・接続対象）
  - `frontend/src/lib/api/client.ts:258-450` — 配線済み enqueue 関数群（`analyzeStack`/`detectDebts`/`detectKnowledgeDebts`/`analyzeGalaxy`/`generateQuiz`/`submitQuiz`/`createRepaymentPr`）+ `getJob`
  - `frontend/src/lib/config/nav.ts:49-128` — サイドバー定義（`comingSoon` / `pill`）
  - `frontend/src/routes/[org]/[project]/+page.svelte` — Overview トップ（cockpit 差込先）
  - `frontend/src/lib/components/overview/overview-dashboard.svelte` — 完了後の合流先
  - `frontend/src/lib/stores/galaxy-store.svelte.ts`（`load`/`loadMock`/`myKc`）/ `quiz-store.svelte.ts`（`loadAvailable`/`availableCount`）/ `agent-store.svelte.ts`（`loadMock`/`tick`/`retry`）— 各 Map のストア
  - `frontend/src/lib/components/galaxy|quiz/coming-soon-placeholder.svelte` — 各サブページの生成 CTA 設置先
  - `frontend/messages/ja.json` / `en.json` — Paraglide 文言（ja 主・en 従）
- 規約
  - `CLAUDE.md` — Svelte 5 runes のみ / shadcn-svelte@latest（`ui/` 読み取り専用・`ui/` 外で合成）/ Tailwind v4 /
    Zod v4（snake_case 保持）/ Paraglide 2.0（ja 主・en 従）/ フロントは kebab-case / PATCH 規約 / 警告を無視しない /
    `bun run check` / `lint` / `test:unit` ゲート
</content>
</invoke>
