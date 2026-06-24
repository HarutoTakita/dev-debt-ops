# 学習プラン: チーム資産優先 → 外部資源候補（Coming Soon プレースホルダ + 画面枠）

## 概要

クイズ結果やナレッジギャップから遷移する **学習プラン画面**（仕様書 §5.4）の
ナビ枠・ルート・Coming Soon プレースホルダを用意する。

学習プランの最大の特徴は **チーム内資産（死蔵 ADR / PR レビューコメント / 社内勉強会動画）を
最優先リソースとして外部資源候補（Udemy・公式 docs 等）より上に浮上させる** ことにある。
本 issue ではこの設計思想を反映した画面の「場所」を確保するところまでを対象とし、
**機能本体（実データ取得・Vector Search・進捗永続化）は実装しない**。

`[org]/learning` ルートと `LearningPlan` / リソースの Zod スキーマ・モックを追加し、
チーム資産優先リストと外部資源候補（二次）のレイアウトを骨組みとして配置する。
実データが揃うまでは `ComingSoonPlaceholder` を表示する。
この画面は将来、ADR ナレッジベース（Wiki 写像・Diátaxis 分類）の入口も兼ねる。

## 背景・目的

ナレッジ負債の返済ループは「検知 → クイズ → ギャップ抽出 → **学習プラン** → 再クイズ」で閉じる
（仕様書 §5.3 → §5.4）。クイズ結果画面（§6.4）は「正解/不正解」ではなく
「あなたが理解していたこと/学ぶ余地」という建設的フレーミングで終わり、
**結果から直接、学習プランへ遷移** する導線が必須となる。本 issue はその遷移先の器を先に用意する。

一般的な学習サービスは外部教材（Udemy・Coursera・技術書）を主役に据える。DevDebtOps はこれを
**意図的に反転** させ、組織内に死蔵された ADR・Slack 議論・勉強会動画を「段階 1: チーム内資産（最優先）」
として外部資源より上に置く（仕様書 §5.4 の優先順序）。これにより、
**組織知が初めて読まれる瞬間** を UI で祝い、チーム資産の再活性化を見える化する。
この「内製資産を最優先で浮上させる」設計は GitLab にも一般的な学習プラットフォームにも存在せず、
DevDebtOps 固有の価値である。GitLab の `wiki_menu.rb`（Plan 配下のナレッジ拠点 IA）や
`snippets_menu`（再利用スニペットライブラリ）は IA とナビ配置の参考にはなるが、
「死蔵資産を学習リソースとして優先提示する」という発想そのものは DevDebtOps 独自である。

将来この画面は ADR ナレッジベースの入口を兼ねる。CLAUDE.md の `docs/`（Diátaxis:
`tutorials/` / `guides/` / `reference/` / `adr/`）構成とリソース分類を整合させ、
GitLab の Wiki が果たす「Plan 配下のナレッジ拠点」役割を DevDebtOps では Diátaxis 写像で実現する。

### 前提 Issue（depends_on）

本 issue は以下の Issue を前提とする。これらが未完了の場合、ナビ枠・遷移導線は仮配線とし、
完成後に正式接続する。

- **`app-shell-super-sidebar-foundation`** — スーパーサイドバー（GitLab 風 IA）の土台。
  学習プランのナビ項目（Plan グルーピング）はこのシェルに追加する。
- **`quiz-repayment-experience`** — クイズ返済体験。クイズ結果画面（§6.4）からの
  「学習プランを見る」遷移元はこの Issue が提供する。本 issue 側は遷移先ルートのみ用意し、
  結果データの受け渡し I/F は最小限のクエリパラメータ（`?from=quiz&attemptId=...`）で仮配線する。

## タスク

### ルーティング・ナビ枠（場所の確保）

- [ ] `frontend/src/routes/[org]/learning/+page.svelte` を新規作成する（学習プラン画面の枠）
- [ ] `frontend/src/routes/[org]/learning/+page.ts`（必要なら）でモックデータをロードする
- [ ] スーパーサイドバー（前提 Issue `app-shell-super-sidebar-foundation`）の **Plan グルーピング**に
  「学習プラン」ナビ項目を追加する（GitLab `work_items_menu.rb` の `PlanMenu` 配下配置を参考）
- [ ] 機能本体は実装せず、ルート + ナビ項目 + Coming Soon プレースホルダ（場所だけ）を用意する

### Coming Soon プレースホルダ

- [ ] `frontend/src/lib/components/common/coming-soon-placeholder.svelte` を新規作成する
  - GitLab の空状態（`Pajamas::EmptyStateComponent` / `GlEmptyState`）パターンを参考にしつつ、
    DevDebtOps ブランドの独自表現（後述の技術詳細「プレースホルダの見た目」を参照）
  - `title` / `description` / `eta`（任意）/ アイコンを props で受ける
- [ ] 学習プラン画面 (`learning/+page.svelte`) で `ComingSoonPlaceholder` を表示する
- [ ] 「チーム資産が初めて読まれる瞬間を祝う」というコンセプトコピーをプレースホルダに含める

### スキーマ + モック

- [ ] `LearningPlan` / 学習リソース（チーム資産・外部資源）の Zod スキーマを
  `frontend/src/lib/api/schemas.ts` に追加する（`learningResourceSchema` / `learningStepSchema` /
  `learningPlanSchema`、リソース種別 `resource_origin: "team" | "external"`）
- [ ] `frontend/src/lib/mocks/learning-plan.ts` にモック学習プランを追加する
  （ADR / 勉強会動画 / PR コメントを段階 1、外部資源を段階 2 として並べる）
- [ ] スキーマから型をエクスポート（`LearningResource` / `LearningStep` / `LearningPlan`）

### リソースリスト UI（骨組み）

- [ ] `frontend/src/lib/components/learning/resource-list.svelte` を新規作成する
  - **チーム資産優先セクション**（最上段）と **外部資源候補セクション（二次）**（下段）に分割
  - チーム資産は「組織内」バッジ・出典（ADR-XXXX / 勉強会 / PR #）・最終アクセス（死蔵バッジ）を強調
- [ ] `frontend/src/lib/components/learning/resource-card.svelte` を新規作成する
  （リソース 1 件の表示。種別アイコン・所要時間・必須/推奨/補助ラベル）
- [ ] Coming Soon 段階ではモックデータでレイアウトのみ確認できる状態にする
  （データ配線は前提 Issue 完了後）

### 遷移導線（仮配線）

- [ ] クイズ結果（§6.4・前提 Issue `quiz-repayment-experience`）から
  `[org]/learning?from=quiz&attemptId=...` への「学習プランを見る」リンクを仮配線する
- [ ] 負債詳細（将来のダッシュボード優先対応リスト §6.1）からの遷移導線も仮プレースホルダで用意する

### 学習プラン進捗トラッキング表示（枠のみ）

- [ ] 学習プランの進捗（完了ステップ数 / 総ステップ数・推定残り時間）を表示する
  プログレス表示の枠を用意する（モック値・Coming Soon 表記）

### i18n

- [ ] Paraglide メッセージ（`Learning_*` 名前空間）を日本語（プライマリ）・英語（セカンダリ）で追加する
  （`Learning_Plan_Title` / `Learning_TeamAssets_Heading` / `Learning_External_Heading` /
  `Learning_ComingSoon_Title` / `Learning_ComingSoon_Body` 等）

## 完了条件

- `[org]/learning` ルートが存在し、認証済みユーザーがアクセスできること
- スーパーサイドバーの Plan グルーピングに「学習プラン」ナビ項目が表示され、当該ルートに遷移できること
- 学習プラン画面に **Coming Soon プレースホルダ**（DevDebtOps ブランド表現）が表示されること
- リソースリストの骨組みが **チーム資産優先（上）→ 外部資源候補（下）** の順で配置されていること
  （モックデータでレイアウト確認可能）
- 進捗トラッキングの表示枠が存在すること（値はモック・Coming Soon 表記でよい）
- `learningPlanSchema` 系の Zod スキーマと型がエクスポートされていること
- **機能本体（実データ取得・Vector Search・進捗永続化）は本 issue では実装しない**こと
  （ルート + ナビ枠 + プレースホルダの「場所だけ」を確保する）
- `bun run check`（svelte-check）と `bun run lint` がパスすること

## 技術詳細

### 画面レイアウト（Coming Soon プレースホルダ表示時）

```
┌──────────────┬────────────────────────────────────────────┐
│ Super Sidebar│  学習プラン                                 │
│  Plan        │  ギャップ: 分散キャッシュ / ADR-0012        │
│   ├ ダッシュ │ ┌──────────────────────────────────────┐   │
│   ├ クイズ   │ │            ✦  COMING SOON              │   │
│   ├ 学習プラン│ │   組織知が初めて読まれる瞬間を、ここで   │   │
│   └ ナレッジ │ │           祝う準備をしています           │   │
│      ベース  │ │   [チーム資産優先 → 外部資源候補] 設計   │   │
│              │ └──────────────────────────────────────┘   │
└──────────────┴────────────────────────────────────────────┘
```

### 画面レイアウト（リソースリスト骨組み・実装後の姿 / 本 issue ではモック）

```
┌────────────────────────────────────────────────────────────┐
│  学習プラン  進捗 ▓▓▓▓░░░░ 2/6 ステップ ・ 残り約 55 分     │
├────────────────────────────────────────────────────────────┤
│  ★ 段階 1: チーム内資産（最優先）  ← DevDebtOps が最上段に浮上 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ [ADR] ADR-0012 DB 死活独立性ポリシー   必須  10分      │  │
│  │        🕸 18 か月読まれていない（死蔵）→ 初の閲覧!     │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ [動画] @alice 勉強会「分散キャッシュ設計」 必須 25分    │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ [PR]  PR #4523 レビュー議論 by @alice    推奨  5分      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  段階 2: 外部資源候補（二次）                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ [Docs] Redis 公式 Caching Patterns       補助  20分     │  │
│  │ [Book] "DDIA" Ch.7 (Kleppmann)           補助  —        │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### コンポーネント構成（kebab-case / Svelte 5 runes / shadcn-svelte / Tailwind v4）

```
frontend/src/routes/[org]/learning/
  +page.svelte                         学習プラン画面の枠（Coming Soon を表示）
  +page.ts                             モック学習プランをロード（任意）

frontend/src/lib/components/common/
  coming-soon-placeholder.svelte       DevDebtOps ブランドの空状態プレースホルダ（汎用）

frontend/src/lib/components/learning/
  resource-list.svelte                 チーム資産優先 → 外部資源候補の 2 セクション
  resource-card.svelte                 リソース 1 件カード（種別・所要時間・必須/推奨/補助）
  plan-progress.svelte                 進捗トラッキング表示の枠（プログレスバー）

frontend/src/lib/mocks/
  learning-plan.ts                     §5.4 の例に沿ったモックプラン

frontend/src/lib/api/schemas.ts        learningResourceSchema 等を追記
```

既存パターンに合わせる点:

- `repo-picker.svelte` / `[org]/+page.svelte` と同様に Svelte 5 runes（`$state` / `$derived` /
  `$props` / `$effect`）のみを使用する（レガシー `$:` / store 不使用）。
- `frontend/src/lib/components/ui/` の shadcn-svelte プリミティブは読み取り専用。
  バッジ・カード等は `ui/` 外のラッパー（`resource-card.svelte` 等）で合成し、
  `$lib/utils.ts` の `cn` でクラスをマージする。
- `[org]/+layout.svelte` のヘッダ + `[org]/+layout.ts` の認証ガードをそのまま継承する。

### プレースホルダの見た目（GitLab 空状態を参考 + DevDebtOps 独自）

GitLab の `Pajamas::EmptyStateComponent`（`title` / `svg_path` / `primary_button_*` / `description`）
の構造を参考にしつつ、DevDebtOps は「死蔵された組織知が初めて読まれる瞬間を祝う」というコンセプトを
ブランド表現として前面に出す（単なる "Nothing here yet" にしない）。

- 中央寄せの空状態。DevDebtOps のブランドアイコン（`frontend/src/lib/assets/favicon.svg` 系）を据える。
- 見出し: 「Coming Soon — 学習プラン」、本文: 「組織知が初めて読まれる瞬間を、ここで祝う準備をしています」。
- 副文で設計思想（チーム資産優先 → 外部資源候補）を 1 行で示す。
- `eta` props が渡された場合のみ「公開予定: …」を小さく表示。

```svelte
<!-- frontend/src/lib/components/common/coming-soon-placeholder.svelte -->
<script lang="ts">
  import { cn } from "$lib/utils";
  import Logo from "$lib/components/logo.svelte";

  type Props = {
    title: string;
    description: string;
    eta?: string;
    class?: string;
  };
  const { title, description, eta, class: className }: Props = $props();
</script>

<div class={cn("flex h-full flex-col items-center justify-center gap-4 px-8 text-center", className)}>
  <Logo class="h-12 w-12 opacity-60" />
  <span class="rounded-full bg-muted px-3 py-1 text-xs font-medium tracking-wide text-muted-foreground">
    COMING SOON
  </span>
  <h2 class="text-xl font-semibold">{title}</h2>
  <p class="max-w-md text-sm text-muted-foreground">{description}</p>
  {#if eta}
    <p class="text-xs text-muted-foreground">公開予定: {eta}</p>
  {/if}
</div>
```

### Zod スキーマ / 型（`frontend/src/lib/api/schemas.ts` に追記）

リソースの出典区分 `resource_origin` で「チーム資産（team）」と「外部資源（external）」を分け、
UI のセクション分割と並び順（team を上）に用いる。スキーマは snake_case フィールドをそのまま保持する
（CLAUDE.md のフロント方針）。

```typescript
// Learning Plan (§5.4)
export const resourceOriginSchema = z.enum(["team", "external"]);
export const resourceKindSchema = z.enum(["adr", "video", "pr_comment", "wiki", "docs", "book", "article", "code"]);
export const resourcePrioritySchema = z.enum(["required", "recommended", "supplementary", "hands_on"]);

export const learningResourceSchema = z.object({
  id: z.string(),
  origin: resourceOriginSchema, // "team" を最優先で上に表示
  kind: resourceKindSchema,
  title: z.string(),
  source_ref: z.string().nullable(), // ADR-0012 / PR #4523 / @alice 勉強会 等
  url: z.string().nullable(),
  estimated_minutes: z.number().nullable(),
  priority: resourcePrioritySchema,
  // 死蔵バッジ: 最後に閲覧されてからの経過（チーム資産の再活性化を可視化）
  dormant_days: z.number().nullable().optional(),
});

export const learningStepSchema = z.object({
  order: z.number(),
  resource: learningResourceSchema,
  completed: z.boolean(),
});

export const learningPlanSchema = z.object({
  id: z.string(),
  gap_concepts: z.array(z.string()), // ["distributed_caching", "ADR-0012", "RedisClient"]
  steps: z.array(learningStepSchema),
  estimated_total_minutes: z.number(),
});

export type ResourceOrigin = z.infer<typeof resourceOriginSchema>;
export type LearningResource = z.infer<typeof learningResourceSchema>;
export type LearningStep = z.infer<typeof learningStepSchema>;
export type LearningPlan = z.infer<typeof learningPlanSchema>;
```

### 想定 API（将来 / 本 issue では未実装・モックのみ）

実装は前提 Issue 完了後。インターフェースのみ記載する（更新操作は PATCH を使用、CLAUDE.md 規約）。

```
GET   /api/v1/learning/plans/{plan_id}                      学習プラン取得
PATCH /api/v1/learning/plans/{plan_id}/steps/{order}        ステップ完了状態の部分更新
POST  /api/v1/learning/plans?attempt_id=...                 クイズ結果から学習プラン生成（§5.4 のプラン生成ロジック）
```

レスポンス形（`learningPlanSchema` に対応）:

```json
{
  "id": "plan_001",
  "gap_concepts": ["distributed_caching", "ADR-0012", "RedisClient"],
  "estimated_total_minutes": 70,
  "steps": [
    { "order": 1, "completed": false, "resource": { "id": "r1", "origin": "team", "kind": "adr",
      "title": "ADR-0012 DB 死活独立性ポリシー", "source_ref": "ADR-0012", "url": null,
      "estimated_minutes": 10, "priority": "required", "dormant_days": 540 } },
    { "order": 2, "completed": false, "resource": { "id": "r2", "origin": "team", "kind": "video",
      "title": "勉強会「分散キャッシュ設計」", "source_ref": "@alice 2023-Q4", "url": null,
      "estimated_minutes": 25, "priority": "required" } },
    { "order": 4, "completed": false, "resource": { "id": "r4", "origin": "external", "kind": "docs",
      "title": "Redis 公式 Caching Patterns", "source_ref": null, "url": "https://redis.io/docs/...",
      "estimated_minutes": 20, "priority": "supplementary" } }
  ]
}
```

### リソースリストの並び順ロジック（team を必ず上に）

```svelte
<!-- frontend/src/lib/components/learning/resource-list.svelte（抜粋） -->
<script lang="ts">
  import type { LearningStep } from "$lib/api/schemas";
  type Props = { steps: LearningStep[] };
  const { steps }: Props = $props();

  // 段階 1: チーム内資産（最優先で上） / 段階 2: 外部資源候補（二次）
  const teamSteps = $derived(steps.filter((s) => s.resource.origin === "team"));
  const externalSteps = $derived(steps.filter((s) => s.resource.origin === "external"));
</script>
```

### ADR ナレッジベース入口（将来 / Diátaxis 写像）

この画面は将来、ADR ナレッジベースの入口を兼ねる。GitLab の Wiki が「Plan 配下のナレッジ拠点」を
担うのに対し、DevDebtOps は CLAUDE.md の `docs/` 構成（Diátaxis: `tutorials/` / `guides/` /
`reference/` / `adr/`）にリソースを写像し、ADR を学習リソースとして第一級で扱う。
本 issue ではこの入口へのナビ項目（Coming Soon）を Plan グルーピングに併置するに留める。

### Knowledge Galaxy 連携（将来 / 仕様書 §5.4 末尾）

学習プランは将来、Mind Odyssey 系統の **Knowledge Galaxy UI**（仕様書 §5.4「Knowledge Galaxy への
可視化」）にも写像される。ギャップ概念を「未踏星域」、学習プランを「探索航路」として描き、ステップ完了で
星が点灯する。本 issue では `learningPlanSchema` の `gap_concepts` / `steps[].completed` を
将来の Galaxy 描画にそのまま流用できる形に揃えるところまでを意識し、Galaxy 本体の描画は実装しない
（別 Issue）。チーム資産優先のリソース提示と Knowledge Galaxy による進捗の可視化は、いずれも
GitLab・一般学習サービスに存在しない DevDebtOps 固有の体験軸である。

## 参考

- 仕様書 §5.4「学習プラン生成（チーム資産 → 外部資源）」 — `/Users/takitaharuto/tech-debt-agent/仕様書.md`
  - 学習リソースの優先順序（段階 1: チーム内資産 → 段階 4: ハンズオン）
  - プラン生成のロジック（`internal_asset_search` → `external_resource_search` → `plan_generator`）
  - 「Knowledge Galaxy への可視化」 — 学習プランの将来連携（未踏星域 / 探索航路）
- 仕様書 §5.3「採点とギャップ抽出」 — 学習プラン生成の入力（ギャップ概念）
- 仕様書 §6.4「クイズ UI」 — 結果から学習プランへ遷移する導線
- 仕様書 §6.1「ダッシュボード」 — 優先対応リストからの将来の遷移元
- CLAUDE.md `docs/`（Diátaxis: `tutorials/` / `guides/` / `reference/` / `adr/`）— ナレッジベースの分類整合
- GitLab 参考実装（IA・ナビ配置・空状態）
  - `/Users/takitaharuto/tech-debt-agent/gitlab/lib/sidebars/projects/menus/wiki_menu.rb`
    — Plan 配下のナレッジ拠点 IA → ADR ナレッジベースの入口配置
  - `/Users/takitaharuto/tech-debt-agent/gitlab/lib/sidebars/projects/menus/snippets_menu.rb`
    — 再利用スニペットライブラリ → 学習スニペットの発想元
  - `/Users/takitaharuto/tech-debt-agent/gitlab/lib/sidebars/projects/menus/work_items_menu.rb`
    — `PlanMenu` 配下グルーピング（`super_sidebar_parent: PlanMenu`）の配置参考
  - `/Users/takitaharuto/tech-debt-agent/gitlab/app/components/pajamas/empty_state_component.rb`
    — `GlEmptyState` 相当の空状態パターン（Coming Soon プレースホルダの構造参考）
- 既存フロント（合わせる対象）
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/routes/[org]/+page.svelte`
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/routes/[org]/+layout.svelte`
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/components/repo/repo-picker.svelte`
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/api/schemas.ts`
  - `/Users/takitaharuto/tech-debt-agent/frontend/src/lib/stores/repo-store.svelte.ts`
- 前提 Issue: `app-shell-super-sidebar-foundation`（スーパーサイドバー土台）、
  `quiz-repayment-experience`（クイズ結果からの遷移元）
