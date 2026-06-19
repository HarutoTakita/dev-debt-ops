# Matrix セクション：負債レジストリ一覧（トークン式フィルタ）+ 負債詳細ビューを実装する（一覧/詳細 + Coming Soon プレースホルダ）

## 概要

Overview の二軸負債マトリクス（§6.1）から各象限・セルをドリルダウンする **二次ビュー** を実装する。

- **一覧** `[org]/matrix`：負債レジストリの一覧。GitLab の `filtered_search_bar_root.vue` を写像した **トークン式フィルタ**（種別・深刻度・担当エージェント・ステータス）+ **ソート**（深刻度 / 検出日 / 推定返済コスト）+ **最近の検索を localStorage 保存**。各行に KC ゲージ・AI 生成確率・関連開発者の理解度・二軸座標から導出した P0–P3 優先度バッジを並べる。
- **詳細** `[org]/matrix/[debtId]`：左に該当コード / 根拠、右にメタパネル（深刻度・種別・担当エージェント・関連 ADR・推定返済コスト）、上部にステータスバッジとアクション（返済 PR 作成 / 無視 / 担当割当）。

このフェーズではバックエンド本体は実装せず、**`CodeDebt` / `KnowledgeDebt` の Zod スキーマ + モックデータ + API クライアント関数（モック差し替え可能なシグネチャ）** で UI を完成させる。返済 PR 作成・担当割当などの **アクションは Coming Soon プレースホルダ**（ボタンの場所と導線だけを用意し、押下時は「準備中」表示）とする。

## 背景・目的

Overview のマトリクス（前提 Issue `overview-debt-matrix-dashboard`）は「組織全体を一目で俯瞰する一次ビュー」である。しかし俯瞰だけでは「で、何を返済すべきか」に答えられない。本 Issue はマトリクスのセル / 象限から「具体的にどの負債が、なぜ危険で、誰が担当するか」へ降りていく **ドリルダウンの二次ビュー** を用意する。

仕様書 §6.1 の優先対応リスト（`P0: src/auth/permissions.ts` …）と §7.1 の `CodeDebt` / `KnowledgeDebt` エンティティを画面に落とし込み、二軸負債モデル（§2.3）の「コード品質 × チーム理解度」をレジストリの各行・各詳細でも一貫して表現する。

### 前提 Issue（depends_on）

- `app-shell-super-sidebar-foundation` — アプリシェル / Super Sidebar の土台。`[org]` レイアウトのナビ枠とルーティング基盤を提供する。
- `overview-debt-matrix-dashboard` — Overview の二軸負債マトリクス。**一次ビュー** であり、本 Issue の一覧 / 詳細はそのセルからの遷移先（二次ビュー）。マトリクスのセルクリック → `[org]/matrix?cell=...` の導線は本 Issue 側で受ける。

### 独自性（GitLab の丸パクリにしない観点）

GitLab の `filtered_search_bar` とラベル文化（`scope::value` の角丸ピル）、`vulnerability_report` の深刻度別一覧は **操作系の骨格** としてのみ借用する。Rosetta 固有の表現は次の通り：

- **一覧を平板な Issue テーブルにしない。** あくまで「二軸マトリクスのドリルダウン」として位置づける。一次ビューはマトリクス、本一覧はその投影である。一覧上部に現在のフィルタ条件を二軸座標（どの象限を見ているか）として常時表示する。
- **優先度バッジ P0–P3 は二軸座標から導出する。** GitLab のように人手で付けた優先度ラベルではなく、`(code_debt_score, 1 − knowledge_coverage)` の座標から自動算出する。バッジのピル内に **コード負債軸・ナレッジ負債軸の 2 本のミニゲージ** を内蔵し、「なぜ P0 なのか」を一目で示す（最危険ゾーンほど両ゲージが満ちる）。
- **担当者アバターは「理解している人」と「形式レビューだけの人」を視覚区別する。** `FileMastery.certified_via`（`quiz` / `authorship` / `review`）に応じてアバターの輪郭を変え、KC の高い理解者と「触ったが理解していない人」を一目で分ける。これは GitLab の単なる assignee アバターには無い、Rosetta のナレッジ負債観点そのものである。

## タスク

### フロント API クライアント / スキーマ（`frontend/src/lib/api/`）

- [ ] `frontend/src/lib/api/schemas.ts` に `CodeDebt` / `KnowledgeDebt` の Zod スキーマを追加する
  - `codeDebtSchema`・`knowledgeDebtSchema`・統合ビュー用 `debtItemSchema`（一覧行）・`debtListSchema`・`debtDetailSchema`
  - 深刻度 `severity: "critical" | "high" | "medium" | "low"`、ステータス（種別ごと）、担当エージェント、`ai_generation_prob`、`knowledge_coverage`(KC)、`assigned_developers`（理解度つき）
- [ ] `frontend/src/lib/api/client.ts` に取得関数を追加する（**シグネチャは本実装と互換、内部はモック返却**）
  - `listDebts(orgSlug, params): Promise<DebtList>`・`getDebt(orgSlug, debtId): Promise<DebtDetail>`
  - アクションは Coming Soon：`createRepaymentPr` / `dismissDebt` / `assignDebt` は **未実装スタブ**（`throw new NotImplementedError("coming_soon")` か `{ status: "coming_soon" }` を返す）
- [ ] `frontend/src/lib/api/mock/debts.ts` を新設し、§6.1 の優先対応リスト相当のモックデータ（最危険 / 理想 / コード返済 / 良 の各象限を網羅）を定義する

### 共通コンポーネント：トークン式フィルタ + ソート + 履歴（`frontend/src/lib/components/filter/`）

- [ ] `filtered-search-bar.svelte` を実装する（GitLab `filtered_search_bar_root.vue` の写像）
  - トークン式フィルタ：`種別:`（code-debt / knowledge-debt）・`深刻度:`（critical / high / medium / low）・`エージェント:`・`ステータス:`（未返済 / 返済中 / 解決済）
  - shadcn-svelte の `popover` / `dropdown-menu` / `input` を `ui/` 外で合成（`ui/` 配下は読み取り専用のため `cn` でラップ）
  - `onfilter`・`onsort` コールバック props（Svelte 5 runes、`$props()`）
- [ ] `sort-control.svelte` を実装する（ソートキー：深刻度 / 検出日 / 推定返済コスト + 昇降順トグル）
- [ ] `recent-searches.svelte.ts` ストアを実装する（`frontend/src/lib/stores/`、`*.svelte.ts` クラスベース runes）
  - GitLab `recent_searches_service.js` 相当を localStorage で再現。キー `rosetta:recent-debt-searches:<orgSlug>`、最大 5 件、`fetch()` / `save()`
- [ ] フィルタ / ソート / トークンのラベルは Paraglide i18n メッセージ（日本語プライマリ）に登録する

### 負債レジストリ一覧（`frontend/src/routes/[org]/matrix/`）

- [ ] `+page.svelte`（一覧）を実装する
  - 上部に `filtered-search-bar` + `sort-control`、その下に現在のフィルタを二軸座標（対象象限）として表示
  - 各行に `debt-list-row.svelte` を描画
- [ ] `frontend/src/lib/components/matrix/debt-list-row.svelte` を実装する（1 行 = 1 負債）
  - KC ゲージ・AI 生成確率・`priority-badge`・担当開発者アバター群
- [ ] `frontend/src/lib/components/matrix/priority-badge.svelte` を実装する
  - 二軸座標から P0–P3 を導出。ピル内にコード負債軸 / ナレッジ負債軸の 2 本ミニゲージを内蔵
- [ ] `frontend/src/lib/components/matrix/kc-gauge.svelte`・`developer-avatar.svelte` を実装する
  - `developer-avatar.svelte` は `certified_via` で「理解者 / 形式レビューのみ」を視覚区別
- [ ] `+page.ts`（`export const ssr = false` 前提）でモック経由のデータロードを行う

### 負債詳細ビュー（`frontend/src/routes/[org]/matrix/[debtId]/`）

- [ ] `+page.svelte`（詳細）を実装する（GitLab `header_area.vue` の「本文 + 右メタパネル + ステータスバッジ + アクション」骨格を写像）
  - 左ペイン：該当コードスニペット（`file-viewer.svelte` を再利用）+ 根拠（`archaeology_notes` / `reason`）
  - 右ペイン：`debt-meta-panel.svelte`
  - 上部：ステータスバッジ + アクション行
- [ ] `frontend/src/lib/components/matrix/debt-meta-panel.svelte` を実装する
  - 深刻度・種別・担当エージェント・関連 ADR・推定返済コストを縦並びで表示
- [ ] `frontend/src/lib/components/matrix/debt-status-badge.svelte`・`debt-actions.svelte` を実装する
  - **`debt-actions.svelte` のボタン（返済 PR 作成 / 無視 / 担当割当）は Coming Soon プレースホルダ**（場所だけ用意し、押下で「準備中」トースト or インライン表示）
- [ ] `+page.ts` で `getDebt` を呼びモックを表示する

### ドリルダウン導線

- [ ] Overview マトリクス（前提 Issue）のセル / 象限クリックを `goto("/[org]/matrix?...")` で受ける入口を `[org]/matrix/+page.ts` 側に用意する（クエリでフィルタ初期化）
- [ ] 一覧の行クリック → `[org]/matrix/[debtId]` への遷移を実装する
- [ ] サイドバー（app-shell）に「Matrix」ナビ枠を追加する（前提 Issue のシェルに項目を足すのみ）

### Coming Soon プレースホルダ

- [ ] アクション（返済 PR 作成 / 無視 / 担当割当）の Coming Soon プレースホルダ表現を実装する
  - GitLab の空状態（empty-state）パターンを参考にしつつ、Rosetta ブランドの独自表現（後述）
- [ ] 一覧が 0 件のときの空状態（フィルタで全件除外 / モック未設定）を Coming Soon 寄りの表現で出す

## 完了条件

- `[org]/matrix` で負債レジストリ一覧が表示され、トークン式フィルタ（種別 / 深刻度 / エージェント / ステータス）で絞り込めること
- ソート（深刻度 / 検出日 / 推定返済コスト）と昇降順切り替えが効くこと
- 直近の検索条件が localStorage に保存され、再訪時に「最近の検索」から復元できること
- 各行に KC ゲージ・AI 生成確率・P0–P3 優先度バッジ（2 本ミニゲージ内蔵）・担当開発者アバター（理解者 / 形式レビューの区別つき）が表示されること
- 行クリックで `[org]/matrix/[debtId]` に遷移し、左に該当コード / 根拠、右にメタパネル、上部にステータスバッジが表示されること
- **アクション（返済 PR 作成 / 無視 / 担当割当）は Coming Soon プレースホルダとして「場所と導線だけ」存在し、押下時に「準備中」と分かる表示が出ること**（機能本体は本 Issue では実装しない）
- データはすべて `CodeDebt` / `KnowledgeDebt` の Zod スキーマで parse されたモックで成立すること（バックエンド未接続でも動作する）
- `bun run check`・`bun run lint` が通ること

## 技術詳細

### ルート / コンポーネント構成

```
frontend/src/
├── routes/[org]/matrix/
│   ├── +page.svelte            # 負債レジストリ一覧（二次ビュー）
│   ├── +page.ts                # クエリ → フィルタ初期化 + listDebts(モック)
│   └── [debtId]/
│       ├── +page.svelte        # 負債詳細（本文 + 右メタパネル + アクション）
│       └── +page.ts            # getDebt(モック)
├── lib/components/filter/
│   ├── filtered-search-bar.svelte   # GitLab filtered_search_bar_root.vue 写像
│   └── sort-control.svelte          # 深刻度 / 検出日 / 推定返済コスト + 昇降順
├── lib/components/matrix/
│   ├── debt-list-row.svelte         # 一覧 1 行
│   ├── priority-badge.svelte        # P0–P3 + 2 本ミニゲージ
│   ├── kc-gauge.svelte
│   ├── developer-avatar.svelte      # 理解者 / 形式レビューの視覚区別
│   ├── debt-meta-panel.svelte       # 右メタパネル
│   ├── debt-status-badge.svelte
│   └── debt-actions.svelte          # Coming Soon プレースホルダ
├── lib/stores/
│   └── recent-searches.svelte.ts    # localStorage 履歴（GitLab recent_searches_service 写像）
└── lib/api/
    ├── schemas.ts                   # codeDebtSchema / knowledgeDebtSchema / debtItemSchema …（追記）
    ├── client.ts                    # listDebts / getDebt / createRepaymentPr(スタブ) …（追記）
    └── mock/debts.ts                # §6.1 優先対応リスト相当のモック
```

既存の `frontend/src/lib/components/repo/file-viewer.svelte` を詳細ビューのコードスニペット表示で再利用する（`path` / `content` / `size` props）。一覧 / 詳細とも `export const ssr = false` の SPA 前提で、`+page.ts` のロードはクライアントで走る。

### 画面レイアウト：一覧 `[org]/matrix`

```
┌──────────────────────────────────────────────────────────────┐
│ 負債レジストリ  ← 対象象限: [最危険ゾーン] (コード品質低 × 理解度低) │
├──────────────────────────────────────────────────────────────┤
│ [ 種別:code-debt × ][ 深刻度:critical × ][ 検索を入力… ]  ⌄最近 │  ← filtered-search-bar
│                                          並び: 深刻度 ▼  ↑↓     │  ← sort-control
├──────────────────────────────────────────────────────────────┤
│ ┌P0─────┐ src/auth/permissions.ts                              │
│ │■■■│■■■│ KC 0.18 ▓░░░░  AI 92%   👤🟢 👤⚪ 👤⚪   重複 · critical │ ← debt-list-row
│ └code│know┘                                          推定 3.5h   │
│ ┌P1─────┐ src/services/user-service.ts                         │
│ │■■■│■░░│ KC 0.41 ▓▓░░░  AI 67%   👤🟢 👤🟢          複雑度 · high │
│ └code│know┘                                          推定 2.0h   │
└──────────────────────────────────────────────────────────────┘
   P バッジ内 左ミニゲージ=コード負債軸 / 右ミニゲージ=ナレッジ負債軸
   👤🟢=クイズ合格の理解者 / 👤⚪=形式レビューのみ（輪郭で区別）
```

### 画面レイアウト：詳細 `[org]/matrix/[debtId]`

```
┌──────────────────────────────────────────────────────────────┐
│ ← Matrix へ戻る    src/auth/permissions.ts   [未返済] ⓟ        │ ← status-badge
│ [返済 PR を作成 (準備中)] [無視 (準備中)] [担当を割当 (準備中)] │ ← debt-actions (Coming Soon)
├───────────────────────────────────┬──────────────────────────┤
│ 該当コード / 根拠                  │ メタパネル                │
│ // src/auth/permissions.ts        │ 深刻度    critical        │
│ export function canAccess(...) {   │ 種別      コード負債(重複)│
│   ...（重複ブロック強調）          │ エージェント Code Debt    │
│ }                                  │ 関連 ADR  ADR-0019        │
│                                    │ 推定返済コスト 3.5h       │
│ ── 考古学ノート ──                 │ KC        0.18            │
│ PR #3789 で AI 生成、自動 approve  │ AI 生成確率 92%           │
│ ADR-0019 に違反する再実装。        │ 担当開発者                │
│                                    │  🟢 alice (quiz)          │
│                                    │  ⚪ bob   (review)         │
└───────────────────────────────────┴──────────────────────────┘
```

### Zod スキーマ / 型（`frontend/src/lib/api/schemas.ts` 追記）

§7.1 の `CodeDebt` / `KnowledgeDebt` を camelCase 変換せず snake_case のまま保持する（既存規約に合わせる）。ただし本一覧 / 詳細は **UI 投影スキーマ** であり、§7.1 の生エンティティから次の通り意図的に変形している（モック段階での前倒し正規化）：

- **`severity` を `float` → `enum` に量子化する。** §7.1 は `severity: float` だが、トークン式フィルタ（`深刻度:critical/high/medium/low`）と GitLab `vulnerability_report` の深刻度別一覧に合わせ、UI 表示・フィルタ用に 4 段階へ離散化する（しきい値は本実装で確定。モックでは直接 enum 値を持つ）。
- **`file_id` を `file_path` + `repo` に展開する。** §7.1 は `file_id` 参照だが、一覧 / 詳細は File を join 済みの読み取りビューなので、表示に必要な `file_path` / `repo` / `code_debt_score` / `knowledge_coverage` / `ai_generation_prob` を File から平坦化して持つ。
- **`assigned_developers`（理解度つき）を `CodeDebt` にも持たせる。** §7.1 では `assigned_developers` は `KnowledgeDebt` のみだが、Rosetta の独自性（「理解者 / 形式レビューのみ」の視覚区別）を **コード負債側でも** 出すため、両種別に `assigned_developers`（`certified_via` + `coverage` つき）を持たせる。これは §7.1 の素朴な assignee には無い Rosetta 拡張である。

```typescript
export const severitySchema = z.enum(["critical", "high", "medium", "low"]);
export const debtKindSchema = z.enum(["code", "knowledge"]);
export const certifiedViaSchema = z.enum(["quiz", "authorship", "review"]);

export const assignedDeveloperSchema = z.object({
  github_handle: z.string(),
  coverage: z.number().min(0).max(1), // KC(file, dev)
  certified_via: certifiedViaSchema, // quiz=理解者 / review=形式レビューのみ
});

export const codeDebtSchema = z.object({
  id: z.string(),
  kind: z.literal("code"),
  file_path: z.string(),
  repo: z.string(),
  type: z.enum(["duplicate", "dead", "complexity", "other"]),
  severity: severitySchema,
  status: z.enum(["open", "in_pr", "resolved", "dismissed"]), // 未返済/返済中/解決済/無視
  detected_at: z.iso.datetime({ offset: true }),
  related_pr: z.string().nullable(),
  related_adr: z.string().nullable(),
  archaeology_notes: z.string(),
  code_debt_score: z.number().min(0).max(1),
  knowledge_coverage: z.number().min(0).max(1), // KC(file)
  ai_generation_prob: z.number().min(0).max(1),
  estimated_repay_hours: z.number(),
  assigned_agent: z.literal("code_debt"),
  assigned_developers: z.array(assignedDeveloperSchema),
});

export const knowledgeDebtSchema = z.object({
  id: z.string(),
  kind: z.literal("knowledge"),
  file_path: z.string(),
  repo: z.string(),
  reason: z.enum(["ai_generated", "author_left", "no_review", "other"]),
  severity: severitySchema,
  status: z.enum(["open", "in_progress", "resolved"]), // 未返済/返済中/解決済
  detected_at: z.iso.datetime({ offset: true }),
  related_adr: z.string().nullable(),
  code_debt_score: z.number().min(0).max(1),
  knowledge_coverage: z.number().min(0).max(1),
  ai_generation_prob: z.number().min(0).max(1),
  estimated_repay_hours: z.number(),
  assigned_agent: z.literal("knowledge_debt"),
  assigned_developers: z.array(assignedDeveloperSchema),
});

export const debtItemSchema = z.discriminatedUnion("kind", [codeDebtSchema, knowledgeDebtSchema]);
export const debtListSchema = z.object({
  debts: z.array(debtItemSchema),
  total: z.number(),
});

export type Severity = z.infer<typeof severitySchema>;
export type DebtItem = z.infer<typeof debtItemSchema>;
export type DebtList = z.infer<typeof debtListSchema>;
```

### API クライアント（`frontend/src/lib/api/client.ts` 追記）

取得系はモックを返し、**シグネチャは本実装と互換**にしておく（後でバックエンド `/api/v1/orgs/{slug}/debts` に差し替え）。アクション系は Coming Soon スタブ。

```typescript
import { MOCK_DEBTS } from "./mock/debts";

export type DebtFilter = {
  kind?: ("code" | "knowledge")[];
  severity?: Severity[];
  agent?: string[];
  status?: string[];
};
export type DebtSort = { key: "severity" | "detected_at" | "estimated_repay_hours"; dir: "asc" | "desc" };

export async function listDebts(orgSlug: string, filter: DebtFilter, sort: DebtSort): Promise<DebtList> {
  // TODO: GET /api/v1/orgs/${orgSlug}/debts に差し替え。現状はモックをフィルタ/ソート。
  const debts = applyFilterSort(MOCK_DEBTS, filter, sort);
  return debtListSchema.parse({ debts, total: debts.length });
}

export async function getDebt(orgSlug: string, debtId: string): Promise<DebtItem> {
  const found = MOCK_DEBTS.find((d) => d.id === debtId);
  if (!found) throw new Error("負債が見つかりません");
  return debtItemSchema.parse(found);
}

// --- Coming Soon（場所だけ用意・本体は未実装） ---
export class ComingSoonError extends Error {
  constructor() {
    super("coming_soon");
  }
}
export async function createRepaymentPr(_orgSlug: string, _debtId: string): Promise<never> {
  throw new ComingSoonError();
}
export async function dismissDebt(_orgSlug: string, _debtId: string): Promise<never> {
  throw new ComingSoonError();
}
export async function assignDebt(_orgSlug: string, _debtId: string, _handle: string): Promise<never> {
  throw new ComingSoonError();
}
```

### 優先度バッジの導出（`priority-badge.svelte`）

二軸座標から P0–P3 を算出し、ピル内に 2 本ミニゲージを描く。GitLab の手動優先度ラベルとは異なり、座標から機械的に導く点が独自性。

```typescript
// code = code_debt_score, know = 1 - knowledge_coverage（理解の欠落度）
export function derivePriority(code: number, know: number): "P0" | "P1" | "P2" | "P3" {
  if (code >= 0.6 && know >= 0.6) return "P0"; // 最危険ゾーン（§2.3 左下）
  if (code >= 0.6 || know >= 0.6) return "P1";
  if (code >= 0.3 || know >= 0.3) return "P2";
  return "P3";
}
```

ピルは `<div>` 内に左右 2 本の縦ミニゲージ（左 = `code`、右 = `know`）を `width`/`height` で表現し、P0 ほど両方が満ちる。Tailwind v4 のトークンで深刻度色（critical=destructive 系）を割り当てる。

> 注：仕様書 §3 の優先度式は `priority = code_debt_score × knowledge_debt_score × business_impact` だが、本フェーズは `business_impact`（事業影響度）が未取得のため省き、二軸座標（`code` × `know`）のしきい値バンドで P0–P3 を近似する。`business_impact` 取り込みは本実装フェーズで `derivePriority` に第 3 軸として追加する。

### 担当者アバターの視覚区別（`developer-avatar.svelte`）

`certified_via` で「理解している人」と「形式レビューだけの人」を分ける（§5.1 KC・§5.5 返済認定の思想）。

- `quiz` / `authorship` かつ `coverage >= 0.7` → 実線リング + 緑系（理解者）
- `review` または `coverage < 0.4` → 破線リング + 灰系（形式レビューのみ / 未理解）

`tooltip`（`ui/tooltip`）で `@handle · KC 0.18 · review` を表示する。

### トークン式フィルタ + 履歴（GitLab 写像）

`filtered-search-bar.svelte` は GitLab `filtered_search_bar_root.vue` の `tokens` / `sortOptions` / `recentSearchesStorageKey` / `onFilter` / `onSort` の構造を Svelte 5 runes に写像する。トークンは `種別` / `深刻度` / `エージェント` / `ステータス` の 4 種。`recent-searches.svelte.ts` は GitLab `recent_searches_service.js` の `fetch()` / `save()` を localStorage で再現する。

```typescript
// frontend/src/lib/stores/recent-searches.svelte.ts
class RecentSearchesStore {
  searches = $state<DebtFilter[]>([]);
  #key = "";
  load(orgSlug: string) {
    this.#key = `rosetta:recent-debt-searches:${orgSlug}`;
    try {
      this.searches = JSON.parse(localStorage.getItem(this.#key) ?? "[]");
    } catch {
      this.searches = [];
    }
  }
  add(filter: DebtFilter) {
    this.searches = [filter, ...this.searches].slice(0, 5); // 最大 5 件
    localStorage.setItem(this.#key, JSON.stringify(this.searches));
  }
}
export const recentSearches = new RecentSearchesStore();
```

### Coming Soon プレースホルダの見た目

GitLab の empty-state パターン（中央配置のイラスト + 見出し + 補足 + 主アクション）を骨格として借りつつ、Rosetta ブランドの独自表現にする。

- アクションボタン（返済 PR 作成 / 無視 / 担当割当）はラベルに「(準備中)」を添え、`disabled` 風の淡色 + 砂時計アイコン。押下で `ComingSoonError` を捕捉し `sonner`（`ui/sonner`）で「この機能はまもなく登場します」トーストを出す。
- 一覧 0 件 / 詳細未接続時の空状態は、Rosetta の「ロゼッタストーン解読中」モチーフ（`logo.svelte` ブランドアイコン + 解読中インジケータ）で、灰色一辺倒の GitLab empty-state とは差別化する。
- 「準備中」は赤系のエラーではなく、ブランドのアクセント色 + 落ち着いた補足文で「これから来る」前向きさを表現する。

## 参考

- 仕様書 `仕様書.md`
  - §2.3 二軸負債モデル（コード品質 × チーム理解度 / 最危険ゾーン）
  - §6.1 ダッシュボード（二軸負債マトリクス・優先対応リスト P0/P1…）— 本一覧の出自
  - §7.1 主要エンティティ（`CodeDebt` / `KnowledgeDebt` / `FileMastery` / `Developer`）— スキーマの根拠
  - §5.1 KC の定義・§5.5 返済認定基準 — 担当者の理解度区別の根拠
- GitLab 参考実装
  - `gitlab/app/assets/javascripts/vue_shared/components/filtered_search_bar/filtered_search_bar_root.vue` — トークン式フィルタ + ソート + 最近の検索の骨格
  - `gitlab/app/assets/javascripts/filtered_search/services/recent_searches_service.js` / `gitlab/app/assets/javascripts/filtered_search/stores/recent_searches_store.js` — localStorage 履歴
  - `gitlab/app/assets/javascripts/repository/components/header_area.vue` — 詳細ビューの「本文 + 右メタパネル + ステータスバッジ + アクション」骨格
  - `gitlab/lib/sidebars/projects/menus/work_items_menu.rb` — ナビ枠 / 詳細ビューの構成参考
  - `gitlab/ee/app/assets/javascripts/security_dashboard/components/shared/vulnerability_report/` — 深刻度別一覧の表現参考
- 既存実装（現行ファイル）
  - `frontend/src/routes/[org]/+page.svelte` — Overview の現行エントリ（マトリクス化は前提 Issue）
  - `frontend/src/lib/components/repo/file-viewer.svelte` — 詳細ビューのコードスニペット表示で再利用
  - `frontend/src/lib/stores/repo-store.svelte.ts` — Svelte 5 クラスベース runes ストアの実装パターン
  - `frontend/src/lib/api/schemas.ts` / `frontend/src/lib/api/client.ts` — Zod スキーマ / クライアント関数の追記先
- 関連 Issue
  - `docs/issue/002-repository-connect-and-viewer.md`（ビューア / ストア / Zod の前例）
  - `docs/issue/004-adk-stack-analysis-agent.md`（エージェント / 解析トレースの前例）
  - 前提：`app-shell-super-sidebar-foundation`・`overview-debt-matrix-dashboard`
