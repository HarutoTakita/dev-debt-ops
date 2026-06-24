# 観測台 Overview に二軸負債マトリクスを実装する（Coming Soon 枠 + 段階的中身）

## 概要

組織トップ画面（`[org]/+page.svelte`）を、リポジトリビューアから **観測台 (Overview)** へと格上げし、仕様書 §6.1 の中核ダッシュボードを主役として配置する。

主役は **二軸負債マトリクス**（ファイルを「コード品質 × チーム理解度 (KC)」の平面に置いた散布図）。これを一次ビューとし、続いて **推移地層グラフ**・**今週の活動サマリ**・**優先対応リスト** を縦に積む。

本 issue は `category=coming-soon`。**負債スコア・KC を算出するバックエンドはまだ存在しない**ため、機能本体（実データ集計・スコアリング API）は実装しない。実装するのは **ナビ枠 + ルート + Coming Soon プレースホルダ（場所だけ）+ モックデータで形を見せる UI** までである。実データが届いたらプレースホルダを外すだけで本番表示に切り替わる構造にする。

## 背景・目的

DevDebtOps の価値は「二軸の技術負債を一目で把握できること」にある。仕様書 §6.1 のダッシュボードはプロダクトの顔であり、ここを最初に作り込むことで「DevDebtOps は何を見せるプロダクトか」を確定させる。

ただし負債スコア・KC を吐くバックエンド（Code Debt Agent / KC 算出）は未実装である（仕様書 §5.1 が KC の算出式を定義し、§10.3 の開発優先順位では KC 算出・PR 生成は週 2〜3 に位置づけられている）。そこで本 issue では **UI の器とモックデータ** を先行実装し、データ未取得時は Coming Soon プレースホルダを表示する。器を先に固めることで、後続の集計 API 実装時に「どんな型を返せばよいか」がフロントから逆算で決まる。

### 前提 Issue（depends_on）

本 issue は以下の 2 つを前提とする。両者の完了後に着手する。

- **app-shell-super-sidebar-foundation** — Overview を置くアプリシェル（スーパーサイドバー）が必要。Overview はサイドバーの最初のナビ項目として登録する。
- **repos-viewer-relocate-and-gitlab-polish** — 現在 `[org]/+page.svelte` を占有しているリポジトリビューア（issue-002 で実装）を `[org]/repos/` 配下へ移設済みであること。本 issue はその移設後に空いた `[org]/+page.svelte` を観測台として作り直す。

### 独自性（GitLab の丸パクリにしない観点）

GitLab のダッシュボード（DevOps スコア・Value Stream・Security ダッシュボード）の主役は、いずれも **open Issue / MR の件数リスト** や **指標カードの格子** である。DevDebtOps はこれを反転させる。

- **一次ビューを散布図にする**：件数リストではなく「コード品質 × KC の二軸プレーン」を画面最上部の主役に置き、リストは画面下部の二次ビューへ格下げする。GitLab が `GlSingleStat` の格子を主役にするのとは構図が逆。
- **4 象限に物語名を与える**：単なる scatter ではなく、各象限を「健全 / 理想 / コード返済 / 最危険」と命名し、左下の **最危険ゾーン**（汚い × 誰も理解していない）へ視線を誘導する。GitLab の象限なしプロットとは別物。
- **返済会計の言葉で語る**：指標は「open 件数」ではなく「KC 44% → 68%」「最危険 23 ファイル」「今週 N 件返済」という **負債返済の会計表現** にする。`trend_indicator.vue` の `trendStyle` を反転利用し、**負債の減少を `success`（緑）** として表示する（GitLab の `TREND_STYLE_DESC`: 上昇=danger / 下降=success に相当）。
- **地層メタファー**：推移は GitLab の緑の草グラフ（積み上げ折れ線）ではなく、**地層断面**として描く。DevDebtOps のブランド語彙「地層 = 負債が堆積する層」（仕様書 §1）を可視化に直結させ、理解の堆積を地層の積み重なりで表現する。

## タスク

### ナビ枠 + ルート（Coming Soon の器）

- [ ] スーパーサイドバー（前提 issue 成果物）の先頭に「観測台 / Overview」ナビ項目を追加し、`/{org}` へリンクする
- [ ] `frontend/src/routes/[org]/+page.svelte` をリポジトリビューアから観測台レイアウトへ作り直す（ビューアは前提 issue で `[org]/repos/` へ移設済み）
- [ ] `<svelte:head>` のタイトルを「観測台 · DevDebtOps」に変更する
- [ ] データ未取得（API 404 / 未集計）時に `ComingSoonPlaceholder` を表示し、その背後にモックデータで描いた本番同等レイアウトを薄く透かす（場所だけ見せる）

### Zod スキーマ + モックデータ（`frontend/src/lib/api/schemas.ts`）

- [ ] `fileDebtSchema`（`path` / `code_debt_score` / `knowledge_coverage` / `priority` / `language` / `business_impact`）を追加する
- [ ] `debtTrendPointSchema`（`week` / `code_debt_score` / `knowledge_coverage`）を追加する
- [ ] `weeklyActivitySchema`（`code_agent_prs` / `code_agent_merged` / `knowledge_agent_quizzes` / `knowledge_agent_passed`）を追加する
- [ ] `overviewSchema`（上記をまとめた組織サマリ）と各 `type` エクスポートを追加する
- [ ] `frontend/src/lib/mock/overview-mock.ts` を新規作成し、仕様書 §11 デモシナリオ（幕 5）の数値（4 週間でコード負債 67→58、KC 44%→68%）に沿ったモック `Overview` を 1 つエクスポートする

### shadcn chart プリミティブ導入

- [ ] `bunx shadcn-svelte@latest add chart` で `frontend/src/lib/components/ui/chart/` を導入する（`layerchart` ベース。`ui/` は読み取り専用なので生成物はそのまま使う）
- [ ] 散布図・地層グラフは `ui/chart` を **ラップした** `frontend/src/lib/components/overview/` 配下の独自コンポーネントで合成する（`ui/` 外で `cn` 合成）

### 二軸負債マトリクス（一次ビュー）

- [ ] `frontend/src/lib/components/overview/debt-matrix.svelte` を実装する
  - 横軸 = チーム理解度 (KC)、縦軸 = コード品質。各ファイルを 1 点としてプロット
  - 4 象限を背景色 + ラベルで描画：左上「コード返済（要ナレッジ）」/ 右上「理想（健全）」/ 左下「最危険ゾーン」/ 右下「返済余地あり」※仕様書 §2.3 の配置に厳密に合わせる
  - 左下の最危険ゾーンを最も濃い `destructive` 系で塗り、点もそこだけ強調して視線を誘導する
  - 点ホバーでファイルパス・両スコアをツールチップ表示（`ui/tooltip`）
- [ ] `frontend/src/lib/components/overview/quadrant-legend.svelte` を実装する（4 象限の名前と一行の物語を凡例として列挙）

### 推移地層グラフ

- [ ] `frontend/src/lib/components/overview/debt-trend-strata.svelte` を実装する
  - `debtTrendPointSchema[]` を時系列で受け取り、コード負債 / KC を **地層断面** として積層描画する
  - 各週を 1 つの地層帯として下から積み、最新週を最上層に置く

### GlSingleStat / TrendIndicator 写像のカード

- [ ] `frontend/src/lib/components/overview/stat-card.svelte` を実装する（GitLab `GlSingleStat` の写像：大きな数値 + ラベル + メタ）
- [ ] `frontend/src/lib/components/overview/trend-indicator.svelte` を実装する（GitLab `trend_indicator.vue` の写像）
  - `trendStyle: "asc" | "desc"` を受け、**`desc`（負債系）では減少を `success`（緑）・増加を `destructive`（赤）に反転** する
- [ ] 「KC」「最危険ファイル数」「今週の返済」をこのカードで表示する

### 今週の活動サマリ + 優先対応リスト（二次ビュー）

- [ ] `frontend/src/lib/components/overview/weekly-activity.svelte` を実装する（Code Agent N PR / Knowledge Agent N クイズ。仕様書 §6.1 の表記に合わせる）
- [ ] `frontend/src/lib/components/overview/priority-list.svelte` を実装する（P0/P1 のファイルパスを優先度バッジ付きで列挙）

### Coming Soon プレースホルダ

- [ ] `frontend/src/lib/components/overview/coming-soon-placeholder.svelte` を実装する（GitLab の空状態パターンを参考にした DevDebtOps ブランド独自表現。下記「技術詳細」参照）
- [ ] Paraglide メッセージ（`messages/ja.json` / `messages/en.json`）に Overview の見出し・象限名・プレースホルダ文言を追加する

## 完了条件

- スーパーサイドバー先頭に「観測台」ナビが表示され、`/{org}` で観測台レイアウトが描画されること
- **機能本体（負債スコア・KC を算出するバックエンド集計）は実装されていないこと**（本 issue の対象外であることが明確であること）
- データ未取得時に `ComingSoonPlaceholder` が表示され、背後にモックデータで描いた本番同等レイアウト（散布図 + 4 象限 + 地層グラフ + 活動サマリ + 優先対応リスト）が透けて見えること
- 二軸負債マトリクスが画面最上部の主役として表示され、4 象限に「健全 / 理想 / コード返済 / 最危険」の名前と物語が付き、左下の最危険ゾーンへ視線が誘導されること
- `TrendIndicator` が負債系指標で減少を緑（`success`）として表示すること
- 推移地層グラフ・今週の活動サマリ・優先対応リストがモックデータで描画されること
- `bun run check`（svelte-check）・`bun run lint` が通ること

## 技術詳細

### 画面レイアウト（観測台 Overview）

```
┌──────────────┬───────────────────────────────────────────────┐
│ Super Sidebar│  観測台 (Overview)                  [ org選択 ]│
│ ▸ 観測台 ◀━━ │ ┌───────────────────────────────────────────┐ │
│ ▸ リポジトリ │ │ [二軸負債マトリクス]   コード品質 ↑       │ │
│ ▸ ...        │ │  コード返済(要ナレ) │      理想(健全)     │ │
│              │ │        ・           │        ・ ・        │ │
│              │ │ ────────────────────┼──────────────────→  │ │ ← KC
│              │ │  最危険ゾーン ●●●   │   返済余地あり ・   │ │
│              │ │  (汚い×誰も理解せず)│  (汚いが皆理解)     │ │
│              │ └───────────────────────────────────────────┘ │
│              │ ┌──────────┬──────────┬──────────────────────┐ │
│              │ │ KC 68%   │最危険23件│ 今週返済 9 件        │ │ ← stat-card
│              │ │ ▲ +24pt  │ ▼ -4 件  │ ▼                    │ │   (負債↓=緑)
│              │ └──────────┴──────────┴──────────────────────┘ │
│              │ ┌───────────────────────────────────────────┐ │
│              │ │ [推移地層グラフ]  負債 67→58 / KC 44→68%  │ │
│              │ │  ▓▓▓▓ 最新週 (最上層)                      │ │
│              │ │  ▒▒▒▒                                      │ │
│              │ │  ░░░░ 4週前 (最下層)                       │ │
│              │ └───────────────────────────────────────────┘ │
│              │ ┌─────────────────────┬─────────────────────┐ │
│              │ │ [今週の活動]        │ [優先対応リスト]    │ │
│              │ │ Code Agent 12 PR    │ P0 src/auth/...ts   │ │
│              │ │  (9 マージ)         │ P1 src/services/.ts │ │
│              │ │ Knowledge 23 クイズ │ P1 ...              │ │
│              │ │  (17 合格)          │                     │ │
│              │ └─────────────────────┴─────────────────────┘ │
└──────────────┴───────────────────────────────────────────────┘
```

### コンポーネント構成

```
frontend/src/routes/[org]/+page.svelte           ← 観測台（主役）。器の組み立て + データ取得
frontend/src/lib/components/overview/
├── debt-matrix.svelte            ← 二軸散布図（一次ビュー）
├── quadrant-legend.svelte        ← 4 象限の名前 + 物語
├── debt-trend-strata.svelte      ← 推移地層グラフ
├── stat-card.svelte              ← GlSingleStat 写像
├── trend-indicator.svelte        ← trend_indicator.vue 写像（trendStyle 反転）
├── weekly-activity.svelte        ← 今週の活動サマリ（二次ビュー）
├── priority-list.svelte          ← P0/P1 優先対応リスト（二次ビュー）
└── coming-soon-placeholder.svelte← データ未取得時のプレースホルダ
frontend/src/lib/components/ui/chart/             ← shadcn-svelte add chart（読み取り専用）
frontend/src/lib/mock/overview-mock.ts            ← モック Overview データ
```

### API・型（schemas.ts へ追加）

実データ集計 API は本 issue では実装しないが、フロントが期待する型を先に確定させる。後続の集計 API（仕様書 §10.3 の週 2〜3 で実装される KC 算出・負債スコアリングの結果を返す）はこの形に合わせて実装する。

```typescript
// frontend/src/lib/api/schemas.ts

export const debtPrioritySchema = z.enum(["P0", "P1", "P2", "P3"]);

// 二軸プレーンの 1 点 = 1 ファイル
export const fileDebtSchema = z.object({
  path: z.string(),
  language: z.string(),
  code_debt_score: z.number(), // 0..1 高いほど汚い
  knowledge_coverage: z.number(), // 0..1 高いほど皆理解（= KC）
  business_impact: z.number(), // 0..1
  priority: debtPrioritySchema, // §2.3 priority = code_debt × knowledge_debt × business_impact
});

export const debtTrendPointSchema = z.object({
  week: z.string(), // ISO 週 or ラベル
  code_debt_score: z.number(),
  knowledge_coverage: z.number(),
});

export const weeklyActivitySchema = z.object({
  code_agent_prs: z.number(),
  code_agent_merged: z.number(),
  knowledge_agent_quizzes: z.number(),
  knowledge_agent_passed: z.number(),
});

export const overviewSchema = z.object({
  org: z.string(),
  generated_at: z.iso.datetime({ offset: true }),
  files: z.array(fileDebtSchema), // 散布図の点
  trend: z.array(debtTrendPointSchema), // 地層グラフ
  activity: weeklyActivitySchema, // 今週の活動
});

export type DebtPriority = z.infer<typeof debtPrioritySchema>;
export type FileDebt = z.infer<typeof fileDebtSchema>;
export type DebtTrendPoint = z.infer<typeof debtTrendPointSchema>;
export type WeeklyActivity = z.infer<typeof weeklyActivitySchema>;
export type Overview = z.infer<typeof overviewSchema>;
```

想定エンドポイント（**本 issue では未実装** — 器のみ。`getOverview()` は実装せずモックを直接読む）：

```
GET /api/v1/orgs/{org}/overview   →  overviewSchema   ※ 後続 issue で実装
```

### 4 象限の物語（仕様書 §2.3 の配置に厳密準拠）

| 象限 | 位置 | コード品質 | KC | 物語名 | 一行の物語 |
|---|---|---|---|---|---|
| 健全 | 右上 | 高（クリーン） | 高 | **理想** | クリーンで皆が理解している。守る。 |
| コード返済 | 左上 | 高（クリーン） | 低 | **コード返済（要ナレッジ）** | きれいだが誰も理解していない。クイズで返済。 |
| 返済余地あり | 右下 | 低（汚い） | 高 | **返済余地あり** | 汚いが皆理解している。リファクタで返済。 |
| 最危険 | 左下 | 低（汚い） | 低 | **最危険ゾーン** | 汚くて誰も理解していない。最優先 (P0)。 |

> 注：仕様書 §2.3 では縦軸=コード品質（上=クリーン）、横軸=チーム理解度（右=皆理解）。散布図でも `code_debt_score` が低い（=クリーン）ほど上、`knowledge_coverage` が高いほど右に配置する。

### TrendIndicator の反転（trend_indicator.vue 写像）

GitLab の `trend_indicator.vue` は `trendStyle` で色を決める：`asc` は上昇=success、`desc` は上昇=danger。DevDebtOps では負債系指標に `desc` を使い、**減少を success（緑）** として表現する。

```svelte
<!-- frontend/src/lib/components/overview/trend-indicator.svelte -->
<script lang="ts">
  type Props = { change: number; trendStyle?: "asc" | "desc" };
  const { change, trendStyle = "asc" }: Props = $props();

  const up = $derived(change > 0);
  // desc: 負債が減る(change<0)と success。GitLab TREND_STYLE_DESC と同じ。
  const colorClass = $derived(
    trendStyle === "desc"
      ? up
        ? "text-destructive"
        : "text-[var(--success)]"
      : up
        ? "text-[var(--success)]"
        : "text-destructive",
  );
  const arrow = $derived(up ? "▲" : "▼");
</script>

<span class={colorClass}>{arrow} {Math.abs(change)}</span>
```

使用例（最危険ファイル数・負債スコアは `desc`、KC は `asc`）：

```svelte
<TrendIndicator change={-4} trendStyle="desc" />  <!-- 最危険 -4件 → 緑 -->
<TrendIndicator change={+24} trendStyle="asc" />  <!-- KC +24pt → 緑 -->
```

### Coming Soon プレースホルダ（DevDebtOps ブランド独自表現）

GitLab の空状態は `gl-empty-state`（中央のイラスト + 見出し + 説明 + CTA）。これを参考にしつつ、DevDebtOps では **地層メタファー** を流用した独自表現にする。

- 背後に **モックデータで描いた本番同等の観測台**を `opacity-40` + `blur-[1px]` + `pointer-events-none` で薄く透かし、「ここに何が出るか」を場所として見せる
- その手前に半透明オーバーレイ + 中央カードを重ねる。カードは地層断面の細いストライプ装飾 + 見出し「観測台はまもなく稼働します」+ 説明「負債スコアと KC の集計が完了すると、この二軸プレーンに自組織のファイルが描かれます」
- CTA は「リポジトリを接続する」（前提 issue の repos ビューアへ遷移）

```svelte
<!-- coming-soon-placeholder.svelte（骨子） -->
<div class="relative h-full">
  <div class="pointer-events-none absolute inset-0 opacity-40 blur-[1px]">
    {@render preview?.()}  <!-- モックで描いた本番レイアウト -->
  </div>
  <div class="absolute inset-0 flex items-center justify-center bg-background/60">
    <div class="max-w-md rounded-lg border bg-card p-6 text-center">
      <div class="mx-auto mb-4 h-2 w-24 space-y-0.5">
        <!-- 地層ストライプ装飾 -->
        <div class="h-0.5 bg-primary/80"></div>
        <div class="h-0.5 bg-primary/50"></div>
        <div class="h-0.5 bg-primary/30"></div>
      </div>
      <h2 class="text-lg font-semibold">観測台はまもなく稼働します</h2>
      <p class="mt-2 text-sm text-muted-foreground">
        負債スコアと KC の集計が完了すると、この二軸プレーンに自組織のファイルが描かれます。
      </p>
    </div>
  </div>
</div>
```

### モックデータ（`overview-mock.ts`）

仕様書 §11 デモシナリオ（幕 5）の数値（4 週間で コード負債 67→58 / KC 44%→68%）に整合させる。最危険ゾーンのファイル件数は同 §11 幕 2 の「左下の最危険ゾーンに 23 ファイル」に合わせる。

```typescript
// frontend/src/lib/mock/overview-mock.ts
import type { Overview } from "$lib/api/schemas";

export const overviewMock: Overview = {
  org: "demo",
  generated_at: new Date().toISOString(),
  files: [
    { path: "src/auth/permissions.ts", language: "ts", code_debt_score: 0.82, knowledge_coverage: 0.21, business_impact: 0.9, priority: "P0" },
    { path: "src/services/user-service.ts", language: "ts", code_debt_score: 0.74, knowledge_coverage: 0.35, business_impact: 0.7, priority: "P1" },
    { path: "src/lib/utils.ts", language: "ts", code_debt_score: 0.18, knowledge_coverage: 0.88, business_impact: 0.3, priority: "P3" },
    // ... 最危険ゾーン(左下)を多めに配置し視線誘導
  ],
  trend: [
    { week: "4週前", code_debt_score: 0.67, knowledge_coverage: 0.44 },
    { week: "3週前", code_debt_score: 0.64, knowledge_coverage: 0.5 },
    { week: "2週前", code_debt_score: 0.61, knowledge_coverage: 0.59 },
    { week: "今週", code_debt_score: 0.58, knowledge_coverage: 0.68 },
  ],
  activity: { code_agent_prs: 12, code_agent_merged: 9, knowledge_agent_quizzes: 23, knowledge_agent_passed: 17 },
};
```

### データ取得フロー（`[org]/+page.svelte`）

issue-002 の `tech-stack-panel.svelte` の `PanelState` パターンを踏襲する。本 issue では集計 API がないため、`getOverview()` は呼ばず **常に未取得扱い → プレースホルダ + モックプレビュー** を表示する。後続 issue で `getOverview()` を実装したら `state` を `"done"` に遷移させるだけでよい。

```svelte
<script lang="ts">
  import { overviewMock } from "$lib/mock/overview-mock";
  import ComingSoonPlaceholder from "$lib/components/overview/coming-soon-placeholder.svelte";
  // ... overview コンポーネント群を import

  // 集計 API は未実装。data は常に null（= Coming Soon）。
  let overview = $state<Overview | null>(null);
</script>

{#if overview}
  <!-- 後続 issue: 実データ表示 -->
{:else}
  <ComingSoonPlaceholder>
    {#snippet preview()}
      <!-- overviewMock で本番同等レイアウトを描画（debt-matrix / 地層 / 活動 / 優先対応） -->
    {/snippet}
  </ComingSoonPlaceholder>
{/if}
```

## 参考

- 仕様書 §2.3「二軸負債モデル」 — 4 象限の配置・物語名・`priority = code_debt × knowledge_debt × business_impact`（`/Users/takitaharuto/tech-debt-agent/仕様書.md`）
- 仕様書 §5.1「Knowledge Coverage (KC)」 — `knowledge_coverage` の定義と低 KC フラグ条件（KC < 0.4）
- 仕様書 §6.1「ダッシュボード」 — 画面構成の出典（二軸マトリクス → 推移グラフ → 今週の活動 → 優先対応リスト）。今週の活動の数値（Code Agent 12 PR / 9 マージ、Knowledge Agent 23 クイズ / 17 合格）もここに準拠
- 仕様書 §11「デモシナリオ」 — モックの基準値の出典（幕 5: 4 週間で コード負債 67→58 / KC 44%→68%、幕 2: 最危険ゾーン 23 ファイル）
- 仕様書 §10.1「MVP に含むもの」・§10.3「開発優先順位」 — 集計バックエンド（KC 算出・PR 生成）が後続フェーズである根拠。本 issue が器のみを実装する裏付け
- GitLab 参考実装（独自性のために**写像**として参照、丸パクリはしない）：
  - `/Users/takitaharuto/tech-debt-agent/gitlab/app/assets/javascripts/analytics/dashboards/components/trend_indicator.vue` — `trendStyle`（`asc`/`desc`）による色反転。DevDebtOps は負債=減少を success に反転利用
  - `/Users/takitaharuto/tech-debt-agent/gitlab/app/assets/javascripts/analytics/devops_reports/components/devops_score.vue` — `GlSingleStat` + `GlTableLite` の比較ダッシュボード構図（stat-card の写像元）
  - `/Users/takitaharuto/tech-debt-agent/gitlab/app/assets/javascripts/analytics/analytics_dashboards/components/visualizations/single_stat.vue` — `GlSingleStat` のプロパティ構成（stat-card の写像元）
  - `/Users/takitaharuto/tech-debt-agent/gitlab/ee/app/assets/javascripts/analytics/dashboards/ai_impact/components/metric_table.vue` — 指標カード格子のレイアウト参考
  - `/Users/takitaharuto/tech-debt-agent/gitlab/ee/app/assets/javascripts/security_dashboard/` — 深刻度別集計（優先度別 P0/P1 集計の参考）
- 現行フロント（作り直し/拡張の対象）：
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/routes/[org]/+page.svelte` — 現状はリポジトリビューア。観測台へ作り直す
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/components/repo/tech-stack-panel.svelte` — `PanelState` のローディング/取得パターンを踏襲
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/api/schemas.ts` — Zod スキーマ + 型の追加先
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/stores/repo-store.svelte.ts` — Svelte 5 クラスベース runes ストアの参考
- shadcn-svelte chart（`layerchart` ベース）: https://shadcn-svelte.com/docs/components/chart
