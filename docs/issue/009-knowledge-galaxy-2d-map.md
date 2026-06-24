# Knowledge Galaxy: 個人理解度マップを実装する（Coming Soon プレースホルダ + 2D MVP）

## 概要

仕様書 §6.2 の **Knowledge Galaxy（個人ビュー）** を、§10 MVP スコープに従って
**3D ではなく 2D マップ / リスト形式**で実装する。

開発者個人の「コード理解の宇宙」を、星域メタファー（星 = マスター済み / 薄星 = 部分理解 /
ブラックホール = 触ったが未理解 / 未踏星域 = 未接触 / ワームホール = 依存接続）で可視化する。

本 issue では **機能本体（実 KC 算出・クイズ連携）は実装しない**。
`[org]/galaxy` という **ナビ枠 + ルート + Coming Soon プレースホルダ**（場所だけ）を用意し、
将来の本実装に向けて **`FileMastery` / 個人 KC の Zod スキーマ + モックデータ**で
2D 星系マップとリストビューの「見た目」を先行して確立する。

- 初期表示は `ComingSoonPlaceholder`（「あなたの星域はまだ観測されていません — 最初のスキャンを実行」）
- モックフラグを有効化すると、2D 星系マップとリストビューがモックデータで描画される
- メタファー語彙と配色（天文台ティール / シアン）だけを先に確立する

## 背景・目的

仕様書 §6.2 は Knowledge Galaxy を「Mind Odyssey 系統の 3D 可視化」と定義するが、
§10.2 で **「Knowledge Galaxy 3D UI は Future（2D マップで代替）」**、§10.1 で
**「個人ビューの簡易版（リスト形式、Galaxy UI は MVP 外）」**と明記されている。
本 issue はこのギャップを埋めるもので、**メタファー語彙と画面の置き場所を MVP で確定**し、
3D 化や実 KC 連携は後続 issue に委ねる。

### 前提 Issue

- **`005-app-shell-super-sidebar-foundation`（depends_on: `app-shell-super-sidebar-foundation`）** — 本 issue が追加する
  `[org]/galaxy` ナビ項目と「自分の KC%」pill は、このアプリシェル / Super Sidebar 基盤に配線する。
  サイドバーのナビ構造・pill コンポーネントが未着手の場合は、最小限のナビリンクで暫定対応する。

### 独自性（GitLab の丸パクリにしない観点）

GitHub / GitLab の緑のコミット草グラフ（contribution graph）は **「活動量 = 貢献」**を示すが、
活動が多い領域 ≠ 理解が深い領域である（AI 生成コードの大量コミットはむしろ負債）。
DevDebtOps は GitLab の `contributors.vue` / `individual_chart.vue`（個人別コミット頻度チャート）から
**「コミット頻度から暗黙知の所在を推定し、バス係数の低い領域をナレッジ負債として可視化する」**
という発想だけを借り、**進捗バーやチェックリストではなく天体メタファー**で描く。

- 活動量グラフではなく **理解の堆積**を星の点灯 / 地形として表現する
- 「やった / やってない」の二値チェックではなく、**KC ∈ [0, 1] を星の光度・色温度**にマッピングする
- 「埋めるべき空白」ではなく **「まだ開拓されていない星系」**として、探索したくなる余白を体感させる
- 配色は GitLab のオレンジ / グレーではなく **天文台ティール / シアン**（暗い宇宙背景に発光する星）

3D（Three.js / WebGL）は MVP では避け、CSS / SVG ベースの 2D マップでメタファー語彙だけを先に確立する。

## タスク

### スキーマ・モック（`frontend/src/lib/api/schemas.ts` / `frontend/src/lib/mocks/galaxy.ts`）

- [ ] `fileMasterySchema`（ファイル単位の個人理解度）を `schemas.ts` に追加する
  - `kc: z.number()`（0–1）、`mastery: masteryStatusSchema`、`module`（星系 = ディレクトリ）、`path` 等
- [ ] `masteryStatusSchema`（`z.enum(["star", "dim_star", "black_hole", "unexplored"])`）を追加する
  - 星 / 薄星 / ブラックホール / 未踏星域に対応
- [ ] `wormholeSchema`（ファイル間依存接続：`from` / `to`）を追加する
- [ ] `starSystemSchema`（星系 = モジュール集合：`module` / `files[]` / 集計 KC）を追加する
- [ ] `personalGalaxySchema`（`developer` / `org_kc` / `systems[]` / `wormholes[]` / `observed: boolean`）を追加する
- [ ] 上記から `FileMastery` / `MasteryStatus` / `Wormhole` / `StarSystem` / `PersonalGalaxy` 型を `z.infer` でエクスポートする
- [ ] `frontend/src/lib/mocks/galaxy.ts` にモックデータ（数モジュール × 各数ファイル、star / dim_star / black_hole / unexplored を混在）を追加する

### ストア（`frontend/src/lib/stores/galaxy-store.svelte.ts`）

- [ ] Svelte 5 クラスベース runes ストア `GalaxyStore` を作成する
  - `galaxy = $state<PersonalGalaxy | null>(null)`、`get observed()`（= 星域観測済みか。`galaxy?.observed` 由来）
  - `myKc = $derived(...)`（自分の KC% を算出 → サイドバー pill 用）
  - `loadMock()`（モックを読み込む）/ `reset()`
  - **本実装ではここを実 API（後続 issue）に差し替える**前提でインターフェースを切る

### 2D 星系マップ（`frontend/src/lib/components/galaxy/`）

- [ ] `star-map.svelte` — 2D 星系マップ全体（暗い宇宙背景 + 星系を格子状に配置）
  - 星系 = モジュール（ディレクトリ）、星 = ファイル
  - KC → 光度（opacity / glow）と色（dim_star → black_hole で青→赤へ色温度変化）にマッピング
  - ワームホール = 星間を結ぶ細い発光ライン（依存接続）
- [ ] `star-system.svelte` — 1 星系（モジュール）の島。所属ファイルの星を内包し、集計 KC をラベル表示
- [ ] `star-node.svelte` — 1 ファイル = 1 星。`mastery` で見た目を分岐（star / dim_star / black_hole / unexplored）
  - hover で tooltip（ファイルパス・KC%・マスター状況）を表示
- [ ] `galaxy-legend.svelte` — メタファー凡例（星 / 薄星 / ブラックホール / 未踏星域 / ワームホール）

### 個人理解度リストビュー（§5.5 個人認定の簡易版）

- [ ] `mastery-list.svelte`（`frontend/src/lib/components/galaxy/mastery-list.svelte`）を実装する
  - ファイルを KC 昇順でリスト表示（ブラックホール = 危険を上位に）
  - 各行に星域メタファーのアイコン / バッジ（star / black_hole 等）・KC%・モジュール名
  - §5.5 の「マスター済み」認定簡易版として `mastery === "star"` を「マスター済み」と表示（実クイズ連携は後続）
- [ ] マップ / リストは `shadcn-svelte` の Tabs（`$lib/components/ui/tabs`）で切り替える

### Coming Soon プレースホルダ（星域未観測）

- [ ] `coming-soon-placeholder.svelte`（`frontend/src/lib/components/galaxy/coming-soon-placeholder.svelte`）を実装する
  - GitLab の `GlEmptyState` パターンを参考にしつつ DevDebtOps ブランドの独自表現（星域メタファー）にする
  - 見出し:「あなたの星域はまだ観測されていません」
  - 説明:「最初のスキャンを実行すると、あなたのコード理解が星として観測されます。」
  - CTA ボタン:「最初のスキャンを実行」（押下時はトースト「Coming Soon」表示。本実装で実スキャンに接続）
  - 開発用に「モックで星域をプレビュー」リンク（`galaxy.loadMock()` を呼ぶ）を併設する

### ルート（`frontend/src/routes/[org]/galaxy/+page.svelte`）

- [ ] `[org]/galaxy/+page.svelte` を新規作成する
  - `galaxy.observed === false`（既定）→ `ComingSoonPlaceholder`
  - 観測済み（モック有効）→ Tabs で `StarMap` / `MasteryList` を表示
  - `<svelte:head>` に `<title>Knowledge Galaxy · DevDebtOps</title>`

### サイドバー配線（前提 Issue 005 `app-shell-super-sidebar-foundation` に依存）

- [ ] Super Sidebar に「Knowledge Galaxy」ナビ項目（`[org]/galaxy` へのリンク）を追加する
- [ ] サイドバー pill に自分の KC%（`galaxy.myKc`）を表示する配線を行う
  - 未観測時は pill 非表示、観測済み時に `{kc}%` を表示

### i18n（`frontend/messages/ja.json` / `frontend/messages/en.json`）

- [ ] 星域メタファー語彙・プレースホルダ文言・凡例ラベルのメッセージキーを追加する（`galaxy_*` 接頭辞）

## 完了条件

- `[org]/galaxy` ルートが存在し、サイドバーから遷移できること（**機能本体は未実装で可**）
- 既定（星域未観測）では `ComingSoonPlaceholder` が表示され、CTA「最初のスキャンを実行」が押下できること
  （押下時は「Coming Soon」トーストで、本実装が未配線であることが明示される）
- `galaxy.loadMock()`（または開発リンク）で星域を観測済みにすると、
  2D 星系マップとリストビューがモックデータで描画されること
- 星系 = モジュール、星 = ファイル、KC → 光度 / 色のマッピングが視覚的に確認できること
- star / dim_star / black_hole / unexplored の 4 状態とワームホール（依存）が凡例どおり描き分けられること
- リストビューが KC 昇順（ブラックホールが上位）で並び、星域メタファーのバッジと KC% を表示すること
- サイドバー pill に自分の KC%（モック値）が表示されること
- `FileMastery` / `PersonalGalaxy` 等の Zod スキーマがモックデータを正しく `parse` できること
- `bun run check` / `bun run lint` がパスすること

## 技術詳細

### 画面レイアウト

#### 星域未観測時（Coming Soon プレースホルダ）

```
┌──────────────────────────────────────────────────┐
│                                                  │
│                  · ✦   ·    ✧                    │
│              ·        🌌        ·                 │
│                   （星雲アイコン）                │
│                                                  │
│         あなたの星域はまだ観測されていません       │
│                                                  │
│   最初のスキャンを実行すると、あなたのコード理解が │
│         星として観測されます。                    │
│                                                  │
│            [ 最初のスキャンを実行 ]               │
│            （開発用）モックで星域をプレビュー      │
│                                                  │
└──────────────────────────────────────────────────┘
```

#### 観測済み（2D 星系マップ）

```
┌──────────────────────────────────────────────────┐
│  [ マップ ] [ リスト ]              自分の KC: 62% │
├──────────────────────────────────────────────────┤
│   ╭─ auth ─────╮        ╭─ services ──────╮       │
│   │  ✦   ●     │~~~~~~~~~│   ✦    ✦   ◌    │       │
│   │ ✧    ●(BH) │ワームホール│  ✧   ●(BH)      │       │
│   │  KC 41%    │        │   KC 70%        │       │
│   ╰────────────╯        ╰─────────────────╯       │
│                                                  │
│   ╭─ utils ────╮                                  │
│   │  ✦  ✦  ✦   │   凡例: ✦星 ✧薄星 ●(BH)穴 ◌未踏  │
│   │   KC 88%   │        ~~~ ワームホール(依存)     │
│   ╰────────────╯                                  │
└──────────────────────────────────────────────────┘
```

#### 観測済み（リストビュー / §5.5 個人認定の簡易版）

```
┌──────────────────────────────────────────────────┐
│  [ マップ ] [ リスト ]                            │
├──────────────────────────────────────────────────┤
│  状態   ファイル                  KC    モジュール │
│  ●(BH) src/auth/permissions.ts   23%   auth       │
│  ●(BH) src/services/user.ts      31%   services   │
│  ✧     src/auth/session.ts       55%   auth       │
│  ✦     src/utils/format.ts       91% ✓ utils      │  ← ✓ = マスター済み
└──────────────────────────────────────────────────┘
```

### コンポーネント構成

```
frontend/src/
├── routes/[org]/galaxy/
│   └── +page.svelte                       # ルート（未観測 → プレースホルダ / 観測済み → Tabs）
├── lib/components/galaxy/
│   ├── coming-soon-placeholder.svelte     # 星域未観測の空状態（DevDebtOps ブランド）
│   ├── star-map.svelte                    # 2D 星系マップ全体
│   ├── star-system.svelte                 # 1 星系（モジュール）の島
│   ├── star-node.svelte                   # 1 ファイル = 1 星（KC → 光度 / 色）
│   ├── galaxy-legend.svelte               # メタファー凡例
│   └── mastery-list.svelte                # 個人理解度リストビュー
├── lib/stores/
│   └── galaxy-store.svelte.ts             # GalaxyStore（runes クラス、myKc を derive）
└── lib/mocks/
    └── galaxy.ts                          # PersonalGalaxy モックデータ
```

### Zod スキーマ・型（`frontend/src/lib/api/schemas.ts` に追記）

`snake_case` フィールドはバックエンド慣習に合わせそのまま保持する（既存スキーマと同様、camelCase 変換はしない）。

```typescript
// Knowledge Galaxy（個人理解度マップ）
// 星=マスター / 薄星=部分理解 / ブラックホール=触ったが未理解 / 未踏星域=未接触
export const masteryStatusSchema = z.enum(["star", "dim_star", "black_hole", "unexplored"]);

export const fileMasterySchema = z.object({
  path: z.string(), // ファイルパス（= 星）
  module: z.string(), // モジュール / ディレクトリ（= 星系）
  kc: z.number().min(0).max(1), // Knowledge Coverage ∈ [0,1]（仕様書 §5.1）
  mastery: masteryStatusSchema,
  // §5.5 個人認定の簡易版: クイズ未連携のため mastery==="star" を "マスター済み" 表示
  mastered: z.boolean().default(false),
});

export const wormholeSchema = z.object({
  from: z.string(), // 依存元ファイルパス
  to: z.string(), // 依存先ファイルパス
});

export const starSystemSchema = z.object({
  module: z.string(),
  kc: z.number().min(0).max(1), // 星系（モジュール）集計 KC = §5.1 の KC(file) 平均
  files: z.array(fileMasterySchema),
});

export const personalGalaxySchema = z.object({
  developer: z.string(),
  org_kc: z.number().min(0).max(1), // サイドバー pill 用の自分の KC%
  observed: z.boolean(), // false の場合は ComingSoonPlaceholder を出す
  systems: z.array(starSystemSchema),
  wormholes: z.array(wormholeSchema),
});

export type MasteryStatus = z.infer<typeof masteryStatusSchema>;
export type FileMastery = z.infer<typeof fileMasterySchema>;
export type Wormhole = z.infer<typeof wormholeSchema>;
export type StarSystem = z.infer<typeof starSystemSchema>;
export type PersonalGalaxy = z.infer<typeof personalGalaxySchema>;
```

### ストア設計（`frontend/src/lib/stores/galaxy-store.svelte.ts`）

```typescript
import type { PersonalGalaxy } from "$lib/api/schemas";
import { mockGalaxy } from "$lib/mocks/galaxy";

class GalaxyStore {
  galaxy = $state<PersonalGalaxy | null>(null);

  // 星域が観測済みか（未観測なら ComingSoonPlaceholder を表示）
  get observed() {
    return this.galaxy?.observed ?? false;
  }

  // サイドバー pill 用: 自分の KC%（0–100 整数）
  myKc = $derived(this.galaxy ? Math.round(this.galaxy.org_kc * 100) : null);

  // MVP: モックを読み込む。本実装ではここを実 API（後続 issue）に差し替える。
  loadMock() {
    this.galaxy = { ...mockGalaxy, observed: true };
  }

  reset() {
    this.galaxy = null;
  }
}

export const galaxy = new GalaxyStore();
```

### KC → 星の見た目マッピング（`star-node.svelte`）

天文台ティール / シアンを基調に、KC の高さで「明るく輝く星」、低さで「赤く危険なブラックホール」へ。

| mastery | 意味 | KC 目安 | 見た目（2D） |
|---|---|---|---|
| `star` | マスター済み | ≥ 0.7 | シアンに強く発光（glow 大・opacity 1.0） |
| `dim_star` | 部分理解 | 0.4–0.7 | ティールで弱く明滅（opacity ~0.5） |
| `black_hole` | 触ったが未理解 | < 0.4（接触あり） | 赤い縁の暗い円（危険色・吸い込む表現） |
| `unexplored` | 未接触 | — | 点線の輪郭のみ（未踏星域・暗い） |

```svelte
<!-- star-node.svelte（抜粋） -->
<script lang="ts">
  import type { FileMastery } from "$lib/api/schemas";
  const { file }: { file: FileMastery } = $props();

  // KC を発光強度に。black_hole は色相を赤へ振る。
  const glow = $derived(Math.max(0.15, file.kc));
  const cls = $derived(
    {
      star: "bg-cyan-300 shadow-[0_0_12px_4px_rgba(103,232,249,0.9)]",
      dim_star: "bg-teal-400/60 shadow-[0_0_6px_2px_rgba(45,212,191,0.5)]",
      black_hole: "border border-red-500/80 bg-red-950 shadow-[0_0_10px_2px_rgba(239,68,68,0.6)]",
      unexplored: "border border-dashed border-slate-600 bg-transparent",
    }[file.mastery],
  );
</script>

<button
  type="button"
  title={`${file.path} · KC ${Math.round(file.kc * 100)}%`}
  style:opacity={glow}
  class={["size-3 rounded-full transition", cls]}
  aria-label={file.path}
></button>
```

### Coming Soon プレースホルダの見た目

GitLab の `GlEmptyState`（中央寄せの SVG イラスト + タイトル + 説明 + CTA）の構図を踏襲しつつ、
イラストは GitLab 流のグレー線画ではなく **暗い宇宙背景に散らばる小さな星（CSS / SVG）**で表現する。
DevDebtOps の他空状態（`repo-picker.svelte` の「GitHub App をインストール」等）と同じ中央寄せレイアウトに揃える。

```svelte
<!-- coming-soon-placeholder.svelte（抜粋） -->
<script lang="ts">
  import { Button } from "$lib/components/ui/button";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import { toast } from "svelte-sonner";

  function startScan() {
    // 本実装で実スキャンへ接続。現状は Coming Soon を明示。
    toast.info("Coming Soon — 最初のスキャンは近日公開です");
  }
</script>

<div class="relative flex h-full flex-col items-center justify-center overflow-hidden bg-slate-950 text-center">
  <!-- 散らばる星（装飾） -->
  <div class="pointer-events-none absolute inset-0 [background:radial-gradient(circle,rgba(103,232,249,0.15)_1px,transparent_1px)] [background-size:32px_32px]"></div>
  <div class="relative max-w-md space-y-4 px-6">
    <p class="text-5xl">🌌</p>
    <h2 class="text-xl font-semibold text-cyan-100">あなたの星域はまだ観測されていません</h2>
    <p class="text-sm text-slate-400">最初のスキャンを実行すると、あなたのコード理解が星として観測されます。</p>
    <Button onclick={startScan} class="bg-cyan-600 hover:bg-cyan-500">最初のスキャンを実行</Button>
    <button onclick={() => galaxy.loadMock()} class="block w-full text-xs text-slate-500 underline">
      （開発用）モックで星域をプレビュー
    </button>
  </div>
</div>
```

### ルート（`frontend/src/routes/[org]/galaxy/+page.svelte`）

```svelte
<script lang="ts">
  import { Tabs, TabsContent, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import ComingSoonPlaceholder from "$lib/components/galaxy/coming-soon-placeholder.svelte";
  import StarMap from "$lib/components/galaxy/star-map.svelte";
  import MasteryList from "$lib/components/galaxy/mastery-list.svelte";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
</script>

<svelte:head><title>Knowledge Galaxy · DevDebtOps</title></svelte:head>

{#if !galaxy.observed || !galaxy.galaxy}
  <ComingSoonPlaceholder />
{:else}
  <Tabs value="map" class="flex h-full flex-col">
    <TabsList><TabsTrigger value="map">マップ</TabsTrigger><TabsTrigger value="list">リスト</TabsTrigger></TabsList>
    <TabsContent value="map" class="flex-1 overflow-hidden"><StarMap galaxy={galaxy.galaxy} /></TabsContent>
    <TabsContent value="list" class="flex-1 overflow-auto"><MasteryList galaxy={galaxy.galaxy} /></TabsContent>
  </Tabs>
{/if}
```

### サイドバー pill 配線（前提 Issue 005 `app-shell-super-sidebar-foundation`）

Super Sidebar のナビ項目「Knowledge Galaxy」の末尾に、`galaxy.myKc` を読む pill を配置する。
GitLab の Super Sidebar の pill（カウントバッジ）と同じ「ナビ項目右端の小バッジ」配置を踏襲する。

```svelte
<!-- 例: サイドバーナビ項目内 -->
{#if galaxy.myKc !== null}
  <span class="ml-auto rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300">
    {galaxy.myKc}%
  </span>
{/if}
```

### MVP / Future の切り分け

| 項目 | 本 issue（2D MVP） | Future（後続 issue） |
|---|---|---|
| 描画 | CSS / SVG ベースの 2D マップ | Three.js / WebGL の 3D 宇宙（§6.2） |
| KC 値 | モックデータ | Knowledge Debt Agent による実 KC 算出（§5.1） |
| マスター認定 | `mastery === "star"` の簡易表示 | クイズ採点（§5.2–5.5）連携 |
| 探索航路 | なし | 学習プランの航路描画（§5.4 / §13.6） |
| データ取得 | `galaxy-store` 内モック | 実 API（`GET /api/v1/.../galaxy` 等） |

## 参考

- **仕様書 §6.2 Knowledge Galaxy（個人ビュー）** — 星 / 薄星 / ブラックホール / 未踏星域 / ワームホール / 星系のメタファー定義
  （`/Users/takitaharuto/tech-debt-agent/仕様書.md`）
- **仕様書 §5.1 KC（Knowledge Coverage）の算出** — `KC(file, dev) ∈ [0,1]`、ファイル全体 KC、組織 KC の定義
- **仕様書 §5.5 返済認定基準（個人単位の認定）** — リストビューの「マスター済み」簡易版の根拠
- **仕様書 §10.1 / §10.2 MVP スコープ** — 「個人ビューの簡易版（リスト形式、Galaxy UI は MVP 外）」「3D UI は Future（2D で代替）」
- **仕様書 §13.6 Knowledge Galaxy 拡張** — 将来拡張の方向性

### GitLab 参考実装（発想の借用元、丸パクリはしない）

- `gitlab/app/assets/javascripts/contributors/components/contributors.vue` — 個人別貢献ビューの全体構成
- `gitlab/app/assets/javascripts/contributors/components/individual_chart.vue` — 個人別コミット頻度チャート（→ 暗黙知の所在・バス係数の可視化に転用）
- `gitlab/app/assets/javascripts/contribution_events/components/contribution_events.vue` — 時系列の貢献イベント（→ 星の点灯メタファーの着想）
- `gitlab/app/assets/javascripts/clusters_list/components/agent_empty_state.vue` — `GlEmptyState` の空状態構図（→ ComingSoonPlaceholder の構図参考）

### 既存実装（パターン踏襲元）

- `frontend/src/lib/components/repo/tech-stack-panel.svelte` — パネル状態管理 / shadcn 配色 / バッジ表現の踏襲元
- `frontend/src/lib/components/repo/repo-picker.svelte` — 中央寄せ空状態 + CTA レイアウトの踏襲元
- `frontend/src/lib/stores/repo-store.svelte.ts` — Svelte 5 クラスベース runes ストアの踏襲元
- `frontend/src/lib/api/schemas.ts` — Zod v4 スキーマ + `z.infer` 型エクスポートの踏襲元
- `frontend/src/routes/[org]/+page.svelte` — `[org]` 配下ルートの構成 / `repo` ストア連携の踏襲元
