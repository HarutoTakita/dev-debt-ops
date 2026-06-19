# アプリシェル + GitLab 風スーパーサイドバー・ナビ基盤を構築する（既存 org レイアウトの全面強化）

## 概要

現在の `[org]/+layout.svelte` は org slug + email + ログアウトしか持たない最小ヘッダーである。これを
GitLab の **スーパーサイドバー型アプリシェル**に作り替え、以降のすべての機能（Galaxy / Matrix / Quizzes /
Agents / Learning など）が乗る土台を用意する。

本 issue は **ナビ基盤・アプリシェル・共通プレースホルダ・ビジュアル言語**の整備が目的であり、
各機能の本体は実装しない。具体的には次の 5 点を整備する。

1. `src/lib/config/nav.ts` に**宣言的ナビ定義**（title / route / icon / pill 取得関数 / 有効条件 / section）を新設
2. **折りたたみ可能セクション**（shadcn collapsible 活用）+ アクティブ自動展開 + 狭幅時アイコンのみ + ピン留め + 右端 pill バッジを Svelte 5 runes で実装
3. **Topbar**（ブランドロゴ + サイドバートグル + 理解の階層パンくず + Cmd+K 起動ボタン枠 + ユーザーメニュー）
4. 全 coming-soon 機能の共通置き場となる **`coming-soon-placeholder` / `empty-state`** ラッパー（GlEmptyState 写像）を 1 つ作り、以降の全 coming-soon Issue がこれを再利用
5. **地層 / 天文台ビジュアル言語の基盤**（`@theme inline` で `--color-success` / `--color-danger` / `--color-subtle`、アンバー / ティール双対アクセント、Fraunces + JetBrains Mono、near-black 背景）を `layout.css` に確立

## 背景・目的

issue-002 で `[org]/+page.svelte` にリポジトリ接続とファイルビューアを実装したが、ナビゲーションは存在せず、
issue-004 で実装した ADK スタック解析の結果も表示する場所がない。Rosetta は仕様書 §6 で

- 二軸負債マトリクス（§6.1）
- Knowledge Galaxy（§6.2）
- クイズ UI（§6.4）
- 各エージェントのナラティブ（§6.5）

という複数の主要画面を持つことが決まっており、それらを横断するナビゲーションとアプリシェルが先に必要になる。
本 issue でその「枠」を作り、後続の各機能 Issue はナビに項目を足してプレースホルダを本実装に差し替えるだけで済むようにする。

### GitLab の丸パクリにしない（独自性の角度）

GitLab のスーパーサイドバーは優れた**構造**（宣言的メニュー組み立て・折りたたみセクション・pill・ピン・フライアウト）を
持つが、Rosetta はその**情報設計と見た目**を意図的にずらす。

- **ナビ第一動詞を `understand` 系に再定義**する。GitLab は Repository / Merge requests / Pipelines という
  「コードを操作する」動詞順だが、Rosetta は Overview / Galaxy / Matrix / Quizzes / Agents / Learning を上位に置き、
  Repos（コード閲覧）は**参照用として末尾に格下げ**する。Rosetta の主語は「コードを書く」ではなく「コードを理解する」だから。
- **pill は open 件数ではなく KC% / 未返済負債残高**を出す。GitLab の「Issues 12」のような件数バッジではなく、
  「KC 62%」「負債 14」のような**負債の健康指標**を右端に出す。
- **配色は Pajamas のニュートラル紫を捨てる**。アンバー（コード負債 = 地層）とティール（ナレッジ負債 = 星）の
  **Twin 双対パレット** + Fraunces セリフ見出し + JetBrains Mono + near-black 背景で、一目で GitLab とは別物に見せる。
- **パンくずは「理解の階層」**（Org KC > Galaxy > 星系 > 星）で表現し、GitLab のようにリポジトリ構造（group / project / path）を
  主語にしない。

この再定義により、構造は GitLab から学びつつ、プロダクトの世界観（地層 × 天文台）を骨格レベルで主張する。

## タスク

### ナビ定義（`frontend/src/lib/config/nav.ts`）

- [ ] 宣言的ナビ定義の型 `NavItem` / `NavSection` を定義する
  - `title`（i18n キー）/ `route`（org 相対パス）/ `icon`（lucide コンポーネント）/ `section` / `pin` 可否
  - `pill?: (ctx) => string | null` — KC% / 未返済負債残高などを返す取得関数（本 issue ではダミー固定値で可）
  - `enabled?: (ctx) => boolean` — 有効条件（例: Repos は接続済みのみ活性、未実装は `comingSoon: true`）
  - `comingSoon?: boolean` — プレースホルダ表示フラグ
- [ ] トップ区分（`add_menu` 順 = 表示順）を以下で定義する
  - **Overview** → **Galaxy** → **Matrix** → **Quizzes** → **Agents** → **Learning** → **Repos** → **Settings**
  - Repos のみ issue-002 で実装済み。それ以外は `comingSoon: true`

### スーパーサイドバー（`frontend/src/lib/components/shell/`）

- [ ] `super-sidebar.svelte` — ナビ定義を `nav.ts` から読み、セクションを描画する親
- [ ] `menu-section.svelte` — shadcn collapsible でセクション折りたたみ。**現在ルートに一致する項目を含むセクションは自動展開**
- [ ] `nav-item.svelte` — 単一項目。アクティブ強調 / pill バッジ（shadcn badge）/ ピン留めトグル / coming-soon 項目は淡色 + 小さな "soon" バッジ
- [ ] 狭幅時（トグル折りたたみ時）は**アイコンのみ**表示。ラベルは tooltip で出す（既存 `ui/tooltip`）
- [ ] **ピン留め**：ピンした項目をサイドバー上部の「ピン留め」セクションに集約。状態は `sidebar-store.svelte.ts` + `localStorage` で永続化
- [ ] 機能本体は実装しない。各セクションのリンク先は coming-soon ルート（下記）に向ける

### Topbar（`frontend/src/lib/components/shell/topbar.svelte`）

- [ ] 左：ブランドロゴ（既存 `logo.svelte`）+ `super-sidebar-toggle.svelte`（サイドバー開閉トグル）
- [ ] 中央：**理解の階層パンくず**（`breadcrumbs.svelte` — Org KC > Galaxy > 星系 > 星 を `page.url` から組み立て）
- [ ] 右：**Cmd+K 起動ボタン枠**（`command-palette-trigger.svelte` — 見た目とショートカット枠だけ。パレット本体は別 issue）
- [ ] 右端：**ユーザーメニュー**（`user-menu.svelte` — shadcn avatar + dropdown-menu。email 表示 + ログアウト。現行 `+layout.svelte` のログアウト処理を移植）

### 共通プレースホルダ（`frontend/src/lib/components/shell/`）

- [ ] `empty-state.svelte` — GlEmptyState 写像のラッパー（illustration スロット + title + description + 主 CTA スロット）
- [ ] `coming-soon-placeholder.svelte` — `empty-state` を内側で使う coming-soon 専用。地層 illustration + 「{機能名} は近日公開」見出し + 説明 + 「ロードマップを見る」CTA
- [ ] **以降の全 coming-soon Issue はこの 2 コンポーネントを再利用**する（重複した空状態を作らない）

### coming-soon ルートの配置

- [ ] ナビと配線するため、機能ごとに**空ページ**を作る（本体は実装しない）
  - `frontend/src/routes/[org]/galaxy/+page.svelte`
  - `frontend/src/routes/[org]/matrix/+page.svelte`
  - `frontend/src/routes/[org]/quizzes/+page.svelte`
  - `frontend/src/routes/[org]/agents/+page.svelte`
  - `frontend/src/routes/[org]/learning/+page.svelte`
  - `frontend/src/routes/[org]/settings/+page.svelte`
- [ ] 各ページは `coming-soon-placeholder` を 1 行で描画するだけにする
- [ ] `frontend/src/routes/[org]/+page.svelte`（Overview）はダッシュボードの coming-soon プレースホルダに差し替える。
      既存のリポジトリビューアは `frontend/src/routes/[org]/repos/+page.svelte` へ移設し、Repos ナビに紐付ける

### アプリシェル（`frontend/src/routes/[org]/+layout.svelte` 全面刷新）

- [ ] 現行の最小ヘッダーを破棄し、`topbar` + `super-sidebar` + コンテンツ領域の 3 ペイン構成に組み替える
- [ ] サイドバー開閉状態を `sidebar-store.svelte.ts` で管理し、Topbar トグルと連動させる
- [ ] 狭幅（モバイル）では shadcn sheet でサイドバーをオーバーレイ表示する

### ビジュアル言語（`frontend/src/routes/layout.css`）

- [ ] `@theme inline` に意味トークンを追加：`--color-success` / `--color-danger` / `--color-subtle`
- [ ] アンバー（`--color-debt-code`）/ ティール（`--color-debt-knowledge`）の**双対アクセント**を定義
- [ ] フォント：見出しに **Fraunces**（`@fontsource-variable/fraunces`）、等幅に既存 **JetBrains Mono** を割り当て、`--font-display` を Fraunces に切り替え
- [ ] ダーク前提の **near-black 背景**（既存 `--color-background-dark` を基盤に、サイドバー / topbar 用の段階を追加）

### shadcn プリミティブ追加導入

- [ ] `bunx shadcn-svelte@latest add badge avatar sheet` で `frontend/src/lib/components/ui/badge|avatar|sheet/` を生成する
- [ ] 既存方針どおり `ui/` は直接編集せず、`shell/` 配下のラッパーで合成する

## 完了条件

- `[org]` 配下のどのルートでも **Topbar + スーパーサイドバー + コンテンツ**の 3 ペインが表示されること
- サイドバーのセクションが折りたたみでき、**現在ルートを含むセクションが自動展開**されること
- サイドバートグルで**アイコンのみ表示**に切り替わり、ラベルが tooltip で出ること
- 項目をピン留めでき、リロード後も**ピン状態が保持**されること（localStorage）
- 各項目の右端に pill（KC% / 負債残高のダミー値）が表示されること
- Galaxy / Matrix / Quizzes / Agents / Learning / Settings の各ルートに遷移すると、**共通 `coming-soon-placeholder`**（地層 illustration + 見出し + 説明 + CTA）が表示されること
- Repos ルートで issue-002 のファイルビューアが従来どおり動作すること
- ユーザーメニューに email が表示され、ログアウトが機能すること
- Cmd+K 起動ボタンの**枠とショートカット表示**が出ること（パレット本体は未実装でよい）
- 見出しが Fraunces、コードが JetBrains Mono、背景が near-black、アクセントがアンバー / ティールで描画されること
- `bun run check` / `bun run lint` がパスすること

## 技術詳細

### 画面レイアウト（アプリシェル全体）

```
┌──────────────────────────────────────────────────────────────────────┐
│ Topbar:  [▤] [Λ Rosetta]   Org KC > Galaxy > 星系 > 星    [⌘K 検索] [◍]│
├──────────────┬───────────────────────────────────────────────────────┤
│ SuperSidebar │ Content (各 +page.svelte / coming-soon-placeholder)    │
│ ─ ピン留め   │                                                       │
│   ★ Matrix   │            ╱╲                                         │
│ ─ UNDERSTAND │           ╱  ╲   地層 illustration                    │
│   ◎ Overview │          ━━━━━━                                       │
│   ✦ Galaxy   62%        Galaxy は近日公開                            │
│   ▦ Matrix   14         コード理解の宇宙をここに描きます              │
│   ? Quizzes  soon       [ ロードマップを見る ]                       │
│   ⚙ Agents   soon                                                    │
│   ↑ Learning soon                                                    │
│ ─ REFERENCE             ※ 狭幅トグル時はアイコンのみ + tooltip        │
│   ▤ Repos                                                            │
│ ─ ────────                                                           │
│   ⚙ Settings                                                         │
└──────────────┴───────────────────────────────────────────────────────┘
```

右端の数値（`62%` / `14`）が pill。`soon` は coming-soon 項目の淡色バッジ。

### コンポーネント構成（`frontend/src/lib/components/shell/`）

```
shell/
├── topbar.svelte                  Topbar コンテナ（ロゴ + トグル + パンくず + ⌘K + ユーザー）
├── super-sidebar.svelte           ナビ定義を読みセクションを描画
├── super-sidebar-toggle.svelte    開閉トグルボタン
├── menu-section.svelte            折りたたみセクション（shadcn collapsible / アクティブ自動展開）
├── nav-item.svelte                単一項目（アクティブ強調 / pill / ピン / coming-soon 淡色）
├── breadcrumbs.svelte             理解の階層パンくず（Org KC > Galaxy > 星系 > 星）
├── command-palette-trigger.svelte ⌘K 起動ボタン枠（ショートカット表示のみ）
├── user-menu.svelte               avatar + dropdown（email + ログアウト）
├── empty-state.svelte             GlEmptyState 写像の汎用空状態ラッパー
└── coming-soon-placeholder.svelte empty-state を使う coming-soon 専用
```

### ナビ定義の型とデータ（`nav.ts`）

GitLab の `panel.rb` における `add_menu` 順 = 表示順、`render?` による表示制御を Rosetta では宣言的配列で表現する。

```typescript
import type { Component } from "svelte";
import { Activity, Sparkles, Grid3x3, HelpCircle, Bot, GraduationCap, FolderGit2, Settings } from "@lucide/svelte";

export type NavContext = { orgSlug: string; repoConnected: boolean };

export interface NavItem {
  id: string;
  title: string; // i18n キー（例: "Nav_Galaxy"）
  route: (ctx: NavContext) => string; // org 相対パス
  icon: Component;
  comingSoon?: boolean;
  enabled?: (ctx: NavContext) => boolean;
  pill?: (ctx: NavContext) => string | null; // KC% / 負債残高（本 issue はダミー）
  pinnable?: boolean;
}

export interface NavSection {
  id: string;
  title: string | null; // null は見出しなしの最終セクション（Settings 等）
  items: NavItem[];
}

// add_menu 順 = 表示順。understand 系を上位、Repos を参照として末尾へ。
export const navSections: NavSection[] = [
  {
    id: "understand",
    title: "Nav_Section_Understand",
    items: [
      { id: "overview", title: "Nav_Overview", icon: Activity, route: (c) => `/${c.orgSlug}` },
      { id: "galaxy", title: "Nav_Galaxy", icon: Sparkles, route: (c) => `/${c.orgSlug}/galaxy`, comingSoon: true, pill: () => "62%" },
      { id: "matrix", title: "Nav_Matrix", icon: Grid3x3, route: (c) => `/${c.orgSlug}/matrix`, comingSoon: true, pill: () => "14" },
      { id: "quizzes", title: "Nav_Quizzes", icon: HelpCircle, route: (c) => `/${c.orgSlug}/quizzes`, comingSoon: true },
      { id: "agents", title: "Nav_Agents", icon: Bot, route: (c) => `/${c.orgSlug}/agents`, comingSoon: true },
      { id: "learning", title: "Nav_Learning", icon: GraduationCap, route: (c) => `/${c.orgSlug}/learning`, comingSoon: true },
    ],
  },
  {
    id: "reference",
    title: "Nav_Section_Reference",
    items: [
      { id: "repos", title: "Nav_Repos", icon: FolderGit2, route: (c) => `/${c.orgSlug}/repos`, enabled: (c) => c.repoConnected },
    ],
  },
  {
    id: "system",
    title: null,
    items: [{ id: "settings", title: "Nav_Settings", icon: Settings, route: (c) => `/${c.orgSlug}/settings`, comingSoon: true }],
  },
];
```

### アクティブ判定とセクション自動展開（Svelte 5 runes）

GitLab の `menu_section.vue` は `data() { isExpanded: this.item.is_active }` で初期展開を決め、
`isActive` を `(!isExpanded || isIconOnly) && is_active` で算出する。Rosetta では runes で同等にする。

```typescript
// menu-section.svelte
let { section }: { section: NavSection } = $props();
const ctx = $derived({ orgSlug: page.params.org, repoConnected: repo.connected !== null });

const hasActive = $derived(section.items.some((i) => isActive(i.route(ctx), page.url.pathname)));
let open = $state(false);
// 現在ルートを含むセクションは自動展開
$effect(() => {
  if (hasActive) open = true;
});

function isActive(route: string, pathname: string): boolean {
  // Overview（/[org]）は完全一致、それ以外は前方一致
  return route.split("/").length === 2 ? pathname === route : pathname.startsWith(route);
}
```

### サイドバーストア（`frontend/src/lib/stores/sidebar-store.svelte.ts`）

```typescript
class SidebarStore {
  collapsed = $state(false); // トグル: アイコンのみ表示
  pinnedIds = $state<string[]>([]);

  constructor() {
    if (typeof localStorage !== "undefined") {
      this.collapsed = localStorage.getItem("rosetta:sidebar:collapsed") === "1";
      this.pinnedIds = JSON.parse(localStorage.getItem("rosetta:sidebar:pinned") ?? "[]");
    }
  }
  toggle() {
    this.collapsed = !this.collapsed;
    localStorage.setItem("rosetta:sidebar:collapsed", this.collapsed ? "1" : "0");
  }
  togglePin(id: string) {
    this.pinnedIds = this.pinnedIds.includes(id) ? this.pinnedIds.filter((p) => p !== id) : [...this.pinnedIds, id];
    localStorage.setItem("rosetta:sidebar:pinned", JSON.stringify(this.pinnedIds));
  }
}
export const sidebar = new SidebarStore();
```

### 共通空状態ラッパー（GlEmptyState 写像）

GitLab の `GlEmptyState`（`svg-path` + `#title` + `#description` + primary action）を Svelte の snippet スロットへ写像する。

```svelte
<!-- empty-state.svelte -->
<script lang="ts">
  import type { Snippet } from "svelte";
  let {
    title,
    description,
    illustration,
    action,
  }: { title: string; description?: string; illustration?: Snippet; action?: Snippet } = $props();
</script>

<div class="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
  {#if illustration}<div class="text-subtle">{@render illustration()}</div>{/if}
  <h2 class="font-display text-2xl">{title}</h2>
  {#if description}<p class="text-muted-foreground">{description}</p>{/if}
  {#if action}<div>{@render action()}</div>{/if}
</div>
```

```svelte
<!-- coming-soon-placeholder.svelte — 地層 illustration を内蔵した coming-soon 専用 -->
<script lang="ts">
  import { Button } from "$lib/components/ui/button";
  import EmptyState from "./empty-state.svelte";
  let { feature, description }: { feature: string; description?: string } = $props();
</script>

<EmptyState title={`${feature} は近日公開`} {description}>
  {#snippet illustration()}
    <!-- 地層: アンバーの堆積層 + ティールの星を 1 つ。Rosetta 独自の Twin ビジュアル -->
    <svg viewBox="0 0 120 80" class="size-32" aria-hidden="true"> ... </svg>
  {/snippet}
  {#snippet action()}
    <Button variant="outline" href="/docs/roadmap">ロードマップを見る</Button>
  {/snippet}
</EmptyState>
```

各 coming-soon ルートは 1 行で再利用する。

```svelte
<!-- routes/[org]/galaxy/+page.svelte -->
<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
</script>
<ComingSoonPlaceholder feature="Knowledge Galaxy" description="コード理解の宇宙をここに描きます。" />
```

### ビジュアル言語トークン（`layout.css` 追記）

```css
/* Rosetta Twin パレット — additive。shadcn 意味トークンは温存 */
@theme inline {
  --font-display: "Fraunces", "Vazirmatn", serif; /* Archivo から差し替え */
  --color-success: oklch(0.72 0.15 165); /* ティール寄りグリーン */
  --color-danger: oklch(0.63 0.21 25);
  --color-subtle: oklch(0.62 0 0);
  --color-debt-code: oklch(0.78 0.15 70); /* アンバー = コード負債 / 地層 */
  --color-debt-knowledge: oklch(0.72 0.11 195); /* ティール = ナレッジ負債 / 星 */
}
```

`@import "@fontsource-variable/fraunces";` を `layout.css` 先頭の font import 群に追加。
near-black 背景は既存 `--color-background-dark`（`oklch(0.185 0 0)`）を基盤に、サイドバー / topbar 用に
1 段暗い面（`oklch(0.16 0 0)`）を割り当てる。

### i18n（Paraglide 2.0）

ナビ・空状態のラベルは `frontend/messages/ja.json` / `en.json` に既存のネスト命名（例: `Org_Create_Title`）に倣って追加する。

```jsonc
// ja.json（抜粋）
{
  "Nav_Section_Understand": "理解する",
  "Nav_Section_Reference": "参照",
  "Nav_Overview": "概要",
  "Nav_Galaxy": "ギャラクシー",
  "Nav_Matrix": "負債マトリクス",
  "Nav_Quizzes": "クイズ",
  "Nav_Agents": "エージェント",
  "Nav_Learning": "学習",
  "Nav_Repos": "リポジトリ",
  "Nav_Settings": "設定",
  "Shell_ComingSoon": "{feature} は近日公開"
}
```

### 現行 → 変更点（ui-refactor）

| 項目 | 現行（issue-002 まで） | 本 issue 後 |
|---|---|---|
| `[org]/+layout.svelte` | org slug + email + ログアウトの最小ヘッダー | Topbar + スーパーサイドバー + コンテンツの 3 ペイン |
| ナビゲーション | なし（Overview しかない） | 宣言的 `nav.ts` + 8 区分のスーパーサイドバー |
| ログアウト | `+layout.svelte` に直書き | `user-menu.svelte` に移設 |
| リポジトリビューア | `[org]/+page.svelte` | `[org]/repos/+page.svelte` に移設、Overview はダッシュボード placeholder |
| 空状態 | 各所でアドホック | 共通 `empty-state` / `coming-soon-placeholder` に統一 |
| 配色・フォント | shadcn ニュートラル + Archivo | Twin パレット（アンバー / ティール）+ Fraunces + near-black |

## 参考

- 仕様書 §6 UI / UX（`仕様書.md`）— §6.1 ダッシュボード、§6.2 Knowledge Galaxy、§6.4 クイズ UI、§6.5 ナラティブ生成（各 coming-soon 画面の将来仕様）
- 仕様書 §2.3 二軸負債モデル、§5.1 検知シグナル（Knowledge Coverage の算出）（pill に出す KC% / 負債残高の意味づけ）
- 仕様書 §10.3 開発優先順位（アプリシェルを先に置く根拠）
- GitLab スーパーサイドバー参考実装
  - `gitlab/app/assets/javascripts/super_sidebar/components/super_sidebar.vue`（シェル全体）
  - `gitlab/app/assets/javascripts/super_sidebar/components/sidebar_menu.vue`（メニュー組み立て）
  - `gitlab/app/assets/javascripts/super_sidebar/components/menu_section.vue`（折りたたみ + アクティブ展開 + フライアウト）
  - `gitlab/app/assets/javascripts/super_sidebar/components/nav_item.vue`（pill + ピン）
  - `gitlab/app/assets/javascripts/super_sidebar/components/super_topbar.vue`（トグル + パンくず + 検索 + ユーザーメニュー）
  - `gitlab/lib/sidebars/panel.rb` / `gitlab/lib/sidebars/projects/super_sidebar_panel.rb`（`add_menu` 順 = 表示順の宣言的組み立て）
  - `gitlab/app/assets/javascripts/clusters_list/components/clusters_empty_state.vue`（GlEmptyState の使い方 = 空状態の写像元）
- 現行フロントエンド
  - `frontend/src/routes/[org]/+layout.svelte`（刷新対象）
  - `frontend/src/routes/[org]/+page.svelte`（Repos へ移設するリポジトリビューア）
  - `frontend/src/lib/components/repo/*`（issue-002 実装、Repos ルートへ移動）
  - `frontend/src/lib/stores/auth.svelte.ts` / `repo-store.svelte.ts`（ユーザー / 接続状態の参照元）
  - `frontend/src/lib/components/logo.svelte`（ブランドロゴ）
  - `frontend/src/routes/layout.css`（ビジュアルトークン追記対象）
- 関連 Issue: issue-002（リポジトリ接続とコンテンツビューア）、issue-004（ADK スタック解析）— 本 issue のシェルに乗る既存機能
