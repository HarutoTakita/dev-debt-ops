# Twin Agent 活動ビューを実装する（ナラティブ思考ストリーム + 実行パイプライン可視化 / モック + Coming Soon）

## 概要

`[org]/agents` ルートに **Twin Agent 活動ビュー** を新設する。Code Debt Agent と
Knowledge Debt Agent それぞれに固有の人格と活動ログを持たせ、

1. **ナラティブ思考ストリーム** — エージェントの一人称の思考ステップ（「3 ファイルの
   類似度を計算中…」「ADR-0019 を発見」「統合を推奨」）と、その判断の **考古学的根拠**
   （初出コミット / AI 生成痕跡 / ADR 参照）を縦積みで物語展開する
2. **エージェント実行パイプライン可視化** — 「検知 → 分析 → 計画 → 返済 → 検証」を
   ステージ列 + ステータスノードで表示し、ライブステータスアイコンと失敗ステップの
   リトライを備える

を実装する。本 issue ではバックエンド実装（実エージェント連携）はまだ行わず、
**Zod スキーマ + モックデータ + UI** を構築し、未配線のサブビューには
`ComingSoonPlaceholder` を置く。GitLab の Merge Request ウィジェットとパイプライン
グラフのレイアウトを着想源としつつ、GitLab Duo 的な汎用チャットボットには **しない**。

## 背景・目的

審査基準①「AI エージェント中心性・必然性」を画面上で最も直接的に体現するのが、この
Twin Agent 活動ビューである。仕様書 §0.2（審査基準への対応）では「両エージェントが
『検知 → 分析 → 計画 → 実行 → 学習』の自律ループを持つ。LLM 推論なしには成立しない設計」
を中心価値に掲げている。ダッシュボード（§6.1）が結果の集約なら、本ビューは
**エージェントが今何を考え、なぜそう動いたか** を見せる「思考の可視化」レイヤーである。

仕様書 §6.5（ナラティブ生成）が要求するのは、単なる機械ログではなく
「今週、`UserService.ts` のリファクタを提案しました。理由は、PR #3789 で AI が生成した
重複コードが ADR-0019 に違反していたためです。…よろしければクイズを受けてみませんか？」
という **一人称の物語** である。これを画面に落とすために、GitLab の MR ウィジェット
（灰色のチェックリストが縦に積層するレイアウト）を **転用** し、各行を機械的チェックでは
なく一人称の思考ステップに置き換える。さらに §4.2（考古学フェーズ）の調査結果を
各ステップに根拠として紐づける。

実エージェント（issue-004 の ADK 基盤の発展形）とライブ接続するのは後続 issue とし、
本 issue では UI とデータ契約（Zod スキーマ）を先に固める。これにより、後でバックエンドが
同じ形の JSON を返すだけで実データに差し替えられる。

### 独自性 — GitLab の丸パクリにしない

GitLab Duo は画面右下に常駐する汎用チャットボットで、ユーザーが質問しないと何も起きない
**受動的 Q&A** である。DevDebtOps はこれを **反面教師** とする。Twin Agent は右下チャットを
持たず、代わりに `[org]/agents` という固有の居場所と人格（Code Debt Agent ＝ 考古学者気質、
Knowledge Debt Agent ＝ 教師気質）を持ち、**能動的に活動ログを語る**。「今週この負債に
気づきました」「@bob さんのレビューが形式的でした、クイズを受けませんか？」と一人称で
**提案する側** に回る。

レイアウトは GitLab から借りるが意味は反転させる。MR ウィジェットの灰色チェックリストは
「CI が通ったか」を示す機械的判定だが、これを **思考ストリーム** に転用し、各行に
「なぜそう考えたか」と考古学的根拠（初出コミット・AI 生成痕跡・ADR 参照）を物語として
添える。パイプライングラフも CI ジョブの状態ではなく **エージェントの自律ループのステージ**
を表す。会話 UI ではなく **自律的行動の可視化** が中心であることが DevDebtOps の差別化点である。

### 前提 Issue

- **`app-shell-super-sidebar-foundation`**（アプリシェル / Super Sidebar 基盤）に依存する。
  `[org]/agents` へのナビゲーションリンク、`[org]/+layout.svelte` のシェル枠は前提 Issue で
  用意される想定。本 issue はその枠内に `agents` ルートを差し込む。前提が未マージの場合は、
  暫定的に現行 `[org]/+layout.svelte` のヘッダーにリンクを追加してよい。

## タスク

### スキーマ + モック（`frontend/src/lib/api/schemas.ts` / `frontend/src/lib/mocks/`）

- [ ] `agentKindSchema`（`z.enum(["code_debt", "knowledge_debt"])`）を追加する
- [ ] `agentProfileSchema`（人格: 名前・ロール・アバター色・口調説明）を追加する
- [ ] `narrativeStepSchema`（一人称思考ステップ + 考古学的根拠）を追加する
- [ ] `agentActivitySchema`（1 件の活動 = ナラティブステップ列 + 関連パイプライン参照）を追加する
- [ ] `pipelineStageSchema` / `pipelineNodeSchema` / `agentPipelineSchema`（検知 → 分析 →
      計画 → 返済 → 検証 のステージ列 + ノード）を追加する
- [ ] 対応する TypeScript 型（`AgentKind` / `AgentProfile` / `NarrativeStep` /
      `AgentActivity` / `AgentPipeline` 等）を `z.infer` でエクスポートする
- [ ] `frontend/src/lib/mocks/agent-activity.ts` にモックデータを作成する
      （Code / Knowledge 双方の人格・活動ログ・パイプラインを各 1〜2 件、§4.2 / §6.5 の
      例文をベースに）

### ストア（`frontend/src/lib/stores/agent-store.svelte.ts`）

- [ ] Svelte 5 クラスベース runes パターンで `AgentStore` を作成する
  - 選択中エージェント（`selectedKind`）、活動ログ一覧、選択中パイプラインを `$state` で保持
  - 当面はモックを読み込む `loadMock()` を持つ（後で API 呼び出しに差し替え）
  - パイプラインノードのライブステータスを進めるシミュレーション（`tickStatus()`）を持つ

### ルート + 画面（`frontend/src/routes/[org]/agents/`）

- [ ] `frontend/src/routes/[org]/agents/+page.svelte` を作成する
  - 上部にエージェント切替（Code Debt Agent / Knowledge Debt Agent のタブ、
    `$lib/components/ui/tabs` を使用）と人格ヘッダー
  - 左ペイン: ナラティブ思考ストリーム、右ペイン: 実行パイプライン可視化
  - `export const ssr = false` 相当（SPA。`+page.ts` は不要なら作らない）

### コンポーネント（`frontend/src/lib/components/agents/`）

- [ ] `agent-profile-header.svelte` — エージェントの人格（名前・ロール・口調）を表示
- [ ] `narrative-stream.svelte` — MR ウィジェット写像の縦積みストリーム
  - 各ステップを一人称テキスト + ステータスアイコンで表示
  - 思考ステップに紐づく考古学的根拠を `narrative-evidence.svelte` で展開（折りたたみ）
- [ ] `narrative-step.svelte` — 1 ステップ（アイコン + 一人称テキスト + 根拠トグル）
- [ ] `narrative-evidence.svelte` — 考古学的根拠（初出コミット / AI 生成痕跡 / ADR 参照）の
      バッジ・リンク表示
- [ ] `agent-pipeline.svelte` — パイプライングラフ写像（ステージ列を横に並べ、各列に
      ノードを縦積み、ステージ間に依存リンク線）
- [ ] `pipeline-stage-column.svelte` — 1 ステージ列（`stage_column_component.vue` 写像）
- [ ] `pipeline-node.svelte` — 1 ノード（`job_item.vue` 写像: CiIcon 写像のステータス +
      失敗時のリトライボタン）
- [ ] `agent-status-icon.svelte` — CiIcon 写像のライブステータスアイコン
      （スキャン中 / 分析中 / 返済 PR 作成中 / 完了 / 失敗）

### Coming Soon プレースホルダ

- [ ] `frontend/src/lib/components/ui/coming-soon-placeholder.svelte` を作成する
      （DevDebtOps ブランドの空状態。後続 issue でも再利用可能な汎用コンポーネント）
- [ ] **実エージェントとのライブ接続は本 issue では実装しない**。ストリームとパイプラインは
      モック駆動とし、まだ配線していない領域（例: 「学習ループ」タブ、実 PR への遷移、
      クイズ提案アクション）には `ComingSoonPlaceholder` を置いて「場所だけ」用意する
- [ ] ナラティブストリーム / パイプライン本体にも、モックである旨を示す控えめな
      「プレビュー（モックデータ）」ラベルを表示する

### i18n（Paraglide）

- [ ] 新規 UI 文字列を Paraglide メッセージとして追加する
      （`messages/ja.json` プライマリ、`messages/en.json` セカンダリ）

## 完了条件

- `[org]/agents` にアクセスすると Code / Knowledge の Twin Agent 切替と人格ヘッダーが
  表示されること
- ナラティブ思考ストリームが、§6.5 / §4.2 の例に沿った **一人称の思考ステップ** を縦積みで
  表示し、各ステップから **考古学的根拠**（初出コミット・AI 生成痕跡・ADR 参照）を
  展開できること
- エージェント実行パイプラインが「検知 → 分析 → 計画 → 返済 → 検証」のステージ列 +
  ノードで表示され、各ノードに CiIcon 写像のライブステータス（スキャン中 / 分析中 /
  返済 PR 作成中 / 完了 / 失敗）が出ること
- 失敗ステータスのノードにリトライボタンが表示され、押下でモック上ステータスが
  「分析中」等に戻ること（ライブ更新シミュレーション）
- **機能本体（実エージェント連携・実 PR/クイズ生成）は実装せず**、未配線領域に
  `ComingSoonPlaceholder`（DevDebtOps ブランドの空状態）が表示されること
- 右下汎用チャットボット（GitLab Duo 型）は **存在しない** こと
- `bun run check`（svelte-check）と `bun run lint`（prettier + eslint）がパスすること

## 技術詳細

### 画面レイアウト

```
┌──────────────────────────────────────────────────────────────────────┐
│  [ Code Debt Agent ]  [ Knowledge Debt Agent ]        プレビュー(モック) │  ← tabs
├──────────────────────────────────────────────────────────────────────┤
│  ◆ アーキ考古学者 / Code Debt Agent                                     │  ← profile-header
│    「重複と規約逸脱を掘り起こし、過去の経緯ごと返済を提案します」        │
├───────────────────────────────┬──────────────────────────────────────┤
│ ナラティブ思考ストリーム      │ エージェント実行パイプライン            │
│ (narrative-stream)            │ (agent-pipeline)                       │
│                               │                                        │
│ ● 3 ファイルの類似度を計算中… │  検知   分析   計画   返済   検証       │
│ ✓ 重複を検出 (3 箇所)         │  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐         │
│   └ 根拠 ▸                    │  │● │─→│● │─→│○ │  │  │  │  │         │
│ ✓ ADR-0019 を発見             │  └──┘  └──┘  └──┘  └──┘  └──┘         │
│   └ 根拠 ▾                    │   完了  分析中 待機  待機  待機          │
│      初出: helpers/time.ts    │                                        │
│        2025-06 / AI 生成痕跡  │  ┌──┐                                  │
│        PR #2456 (レビューなし) │  │✗ │ 返済PR作成 失敗   [ リトライ ]    │
│      ADR: ADR-0019 (date-fns) │  └──┘                                  │
│ ● 統合を推奨…                 │                                        │
│                               │  ── Coming Soon ──────────────         │
│                               │   学習ループの可視化（準備中）           │
└───────────────────────────────┴──────────────────────────────────────┘
```

### コンポーネント構成

```
frontend/src/routes/[org]/agents/+page.svelte
  ├── components/agents/agent-profile-header.svelte
  ├── components/agents/narrative-stream.svelte
  │     └── components/agents/narrative-step.svelte
  │           ├── components/agents/agent-status-icon.svelte
  │           └── components/agents/narrative-evidence.svelte
  ├── components/agents/agent-pipeline.svelte
  │     └── components/agents/pipeline-stage-column.svelte   ← stage_column_component.vue 写像
  │           └── components/agents/pipeline-node.svelte     ← job_item.vue 写像
  │                 └── components/agents/agent-status-icon.svelte  ← CiIcon 写像
  └── components/ui/coming-soon-placeholder.svelte
```

ストア・モックは以下。

```
frontend/src/lib/stores/agent-store.svelte.ts        ← Svelte 5 クラスベース runes
frontend/src/lib/mocks/agent-activity.ts             ← モックデータ
frontend/src/lib/api/schemas.ts                      ← Zod スキーマ + 型を追記
```

UI プリミティブは `frontend/src/lib/components/ui/`（読み取り専用）の `tabs` /
`collapsible` / `tooltip` / `button` / `separator` / `scroll-area` を合成して使う。
ベースプリミティブは編集せず、`agents/` 配下のラッパーで構成し `$lib/utils.ts` の `cn` で
クラスをマージする。

### Zod スキーマ + 型（`schemas.ts` への追記）

```typescript
// Twin Agent
export const agentKindSchema = z.enum(["code_debt", "knowledge_debt"]);

export const agentProfileSchema = z.object({
  kind: agentKindSchema,
  name: z.string(), // 例: "アーキ考古学者"
  role: z.string(), // 例: "Code Debt Agent"
  accent: z.string(), // ブランドアクセント色トークン名
  tagline: z.string(), // 一人称の自己紹介
});

// ライブステータス（CiIcon 写像）
export const agentStatusSchema = z.enum([
  "scanning", // スキャン中
  "analyzing", // 分析中
  "creating_pr", // 返済 PR 作成中
  "running_quiz", // クイズ実施中（Knowledge Agent）
  "succeeded", // 完了
  "failed", // 失敗
  "pending", // 待機
]);

// 考古学的根拠（§4.2）
export const narrativeEvidenceSchema = z.object({
  type: z.enum(["first_commit", "ai_generated", "adr_reference", "pr_review"]),
  label: z.string(), // 例: "ADR-0019 (date-fns で集約)"
  detail: z.string().nullable(), // 例: "helpers/time.ts 2025-06 / AI 生成痕跡"
  href: z.string().nullable(), // PR/ADR/コミットへのリンク（モックでは null 可）
});

// 一人称の思考ステップ（§6.5 ナラティブ）
export const narrativeStepSchema = z.object({
  id: z.string(),
  status: agentStatusSchema,
  // 一人称テキスト 例: "3 ファイルの類似度を計算中…"
  message: z.string(),
  evidence: z.array(narrativeEvidenceSchema),
  created_at: z.iso.datetime({ offset: true }),
});

export const agentActivitySchema = z.object({
  id: z.string(),
  kind: agentKindSchema,
  // 物語の見出し 例: "UserService.ts のリファクタを提案"
  headline: z.string(),
  steps: z.array(narrativeStepSchema),
  pipeline_id: z.string(), // 関連する実行パイプライン
  created_at: z.iso.datetime({ offset: true }),
});

// 実行パイプライン（検知 → 分析 → 計画 → 返済 → 検証）
export const pipelineNodeSchema = z.object({
  id: z.string(),
  label: z.string(),
  status: agentStatusSchema,
  retryable: z.boolean(), // failed のとき true
});

export const pipelineStageSchema = z.object({
  key: z.enum(["detect", "analyze", "plan", "repay", "verify"]),
  label: z.string(), // 検知 / 分析 / 計画 / 返済 / 検証
  nodes: z.array(pipelineNodeSchema),
});

export const agentPipelineSchema = z.object({
  id: z.string(),
  kind: agentKindSchema,
  stages: z.array(pipelineStageSchema),
});

export type AgentKind = z.infer<typeof agentKindSchema>;
export type AgentProfile = z.infer<typeof agentProfileSchema>;
export type AgentStatus = z.infer<typeof agentStatusSchema>;
export type NarrativeEvidence = z.infer<typeof narrativeEvidenceSchema>;
export type NarrativeStep = z.infer<typeof narrativeStepSchema>;
export type AgentActivity = z.infer<typeof agentActivitySchema>;
export type PipelineNode = z.infer<typeof pipelineNodeSchema>;
export type PipelineStage = z.infer<typeof pipelineStageSchema>;
export type AgentPipeline = z.infer<typeof agentPipelineSchema>;
```

> 注: 既存スキーマと同様、snake_case フィールドはそのまま保持する（camelCase 変換はまだ
> 行わない）。後でバックエンドが同形の JSON を返すだけで実データに差し替えられる。

### ストア設計（`agent-store.svelte.ts`）

```typescript
import type { AgentActivity, AgentKind, AgentPipeline, AgentProfile } from "$lib/api/schemas";
import { MOCK_PROFILES, MOCK_ACTIVITIES, MOCK_PIPELINES } from "$lib/mocks/agent-activity";

class AgentStore {
  selectedKind = $state<AgentKind>("code_debt");
  profiles = $state<AgentProfile[]>([]);
  activities = $state<AgentActivity[]>([]);
  pipelines = $state<AgentPipeline[]>([]);

  profile = $derived(this.profiles.find((p) => p.kind === this.selectedKind) ?? null);
  visibleActivities = $derived(this.activities.filter((a) => a.kind === this.selectedKind));

  loadMock() {
    this.profiles = MOCK_PROFILES;
    this.activities = MOCK_ACTIVITIES;
    this.pipelines = MOCK_PIPELINES;
  }

  // 失敗ノードのリトライ（モック上のライブ更新シミュレーション）
  retry(pipelineId: string, nodeId: string) {
    const node = this.pipelines
      .find((p) => p.id === pipelineId)
      ?.stages.flatMap((s) => s.nodes)
      .find((n) => n.id === nodeId);
    if (node) {
      node.status = "analyzing";
      node.retryable = false;
    }
  }
}

export const agents = new AgentStore();
```

### ナラティブ思考ストリーム（MR ウィジェット写像）

GitLab の `job_item.vue`（`gitlab/app/assets/javascripts/ci/pipeline_details/graph/components/job_item.vue`）
は `status.icon` でステータスアイコンを出し、失敗時に `ActionComponent` でリトライを出す。
このパターンを **思考ステップ行** に転用する。違いは、ステータスが「CI 結果」ではなく
「エージェントの思考フェーズ」であり、行テキストが一人称（§6.5）で、根拠（§4.2）が
折りたたみで付くこと。

```svelte
<!-- narrative-step.svelte（抜粋） -->
<script lang="ts">
  import type { NarrativeStep } from "$lib/api/schemas";
  import AgentStatusIcon from "./agent-status-icon.svelte";
  import NarrativeEvidence from "./narrative-evidence.svelte";
  import * as Collapsible from "$lib/components/ui/collapsible";

  let { step }: { step: NarrativeStep } = $props();
  let open = $state(false);
</script>

<div class="flex items-start gap-2 border-l-2 border-muted py-2 pl-3">
  <AgentStatusIcon status={step.status} />
  <div class="min-w-0 flex-1">
    <p class="text-sm">{step.message}</p>
    {#if step.evidence.length > 0}
      <Collapsible.Root bind:open>
        <Collapsible.Trigger class="text-xs text-muted-foreground hover:text-foreground">
          根拠 {open ? "▾" : "▸"}
        </Collapsible.Trigger>
        <Collapsible.Content class="mt-1 space-y-1">
          {#each step.evidence as e (e.label)}
            <NarrativeEvidence evidence={e} />
          {/each}
        </Collapsible.Content>
      </Collapsible.Root>
    {/if}
  </div>
</div>
```

### エージェント実行パイプライン可視化（パイプライングラフ写像）

GitLab の `stage_column_component.vue` はステージ名 + そのステージのジョブ群（`groups`）を
縦に積み、`linked_pipeline.vue` がステージ列を依存リンクで横に連結する。本ビューでは
**検知 / 分析 / 計画 / 返済 / 検証** の 5 ステージを横に並べ、各列にノードを縦積みし、
列間を矢印リンクで結ぶ。ライブステータスは `last_commit.vue` の CiIcon が GraphQL
subscription / ポーリングで更新される挙動（`gitlab/app/assets/javascripts/repository/components/last_commit.vue`）
を着想源とし、本 issue ではストアの `tickStatus()`（モックタイマー）で擬似的にライブ更新する。

```svelte
<!-- pipeline-node.svelte（抜粋）— job_item.vue 写像 -->
<script lang="ts">
  import type { PipelineNode } from "$lib/api/schemas";
  import { agents } from "$lib/stores/agent-store.svelte";
  import AgentStatusIcon from "./agent-status-icon.svelte";
  import { Button } from "$lib/components/ui/button";

  let { node, pipelineId }: { node: PipelineNode; pipelineId: string } = $props();
</script>

<div class="flex items-center gap-2 rounded border bg-card px-2 py-1.5">
  <AgentStatusIcon status={node.status} />
  <span class="truncate text-xs">{node.label}</span>
  {#if node.retryable}
    <Button variant="ghost" size="sm" class="ml-auto h-6 px-2 text-xs" onclick={() => agents.retry(pipelineId, node.id)}>
      リトライ
    </Button>
  {/if}
</div>
```

### CiIcon 写像のライブステータスアイコン（`agent-status-icon.svelte`）

GitLab の CiIcon が `status_success` / `status_running` 等のアイコン名で状態を描き分ける
のと同様、`AgentStatus` を DevDebtOps 独自のアイコン + 色に写像する。アイコンは既存依存の
範囲（Lucide 等）で表現し、`running` 系（スキャン中 / 分析中 / 返済 PR 作成中 / クイズ中）は
回転アニメーションでライブ感を出す。

| `AgentStatus` | 意味 | 表現 |
|---|---|---|
| `scanning` | スキャン中 | 回転スピナー（青） |
| `analyzing` | 分析中 | 回転スピナー（青） |
| `creating_pr` | 返済 PR 作成中 | 回転スピナー（紫） |
| `running_quiz` | クイズ実施中 | 回転スピナー（緑） |
| `succeeded` | 完了 | チェック（緑） |
| `failed` | 失敗 | バツ（赤） + リトライ可 |
| `pending` | 待機 | 中空円（グレー） |

### Coming Soon プレースホルダ（`coming-soon-placeholder.svelte`）

GitLab の空状態（`gl-empty-state`: 中央寄せのイラスト + 見出し + 説明 + アクション）の
**構造** を借りつつ、見た目は DevDebtOps ブランドで独自に表現する。汎用コンポーネントとして
作り、未配線領域（学習ループ可視化・実 PR 遷移・クイズ提案アクション等）に置く。

```svelte
<!-- coming-soon-placeholder.svelte（抜粋） -->
<script lang="ts">
  import Logo from "$lib/components/logo.svelte";
  let { title, description }: { title: string; description?: string } = $props();
</script>

<div class="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 p-8 text-center">
  <div class="opacity-40"><Logo /></div>
  <p class="text-sm font-medium">{title}</p>
  {#if description}
    <p class="max-w-xs text-xs text-muted-foreground">{description}</p>
  {/if}
  <span class="rounded-full border px-2 py-0.5 text-[10px] tracking-wide text-muted-foreground uppercase">Coming Soon</span>
</div>
```

ブランド独自表現の指針: GitLab の白背景 + グレーイラストではなく、DevDebtOps の
ロゴ（`frontend/src/lib/components/logo.svelte`）を淡く配置し、破線ボーダー + `muted` 背景で
「ここに将来エージェントの活動が流れる」という余白を演出する。フルカラーのダミー UI は
置かず、あくまで「場所だけ」を示す。

### 現行ファイルとの関係

| 現行ファイル | 本 issue での扱い |
|---|---|
| `frontend/src/routes/[org]/+page.svelte` | 変更しない（リポジトリビューア。本ビューは別ルート `agents/`） |
| `frontend/src/routes/[org]/+layout.svelte` | 前提 Issue 未マージ時のみ、暫定で `agents` への導線を追加 |
| `frontend/src/lib/stores/repo-store.svelte.ts` | 変更しない（`agent-store.svelte.ts` を新規に倣って作る） |
| `frontend/src/lib/api/schemas.ts` | Twin Agent 関連スキーマ + 型を **追記** |
| `frontend/src/lib/components/ui/` | 読み取り専用。`tabs`/`collapsible`/`tooltip`/`button` を合成のみ |

## 参考

### 仕様書（`仕様書.md`）

- **§0.2 審査基準への対応①**（エージェント中心性 / 自律ループ「検知 → 分析 → 計画 → 実行 → 学習」）
  — 本ビューの中心価値
- **§4.1 検知シグナル / §4.2 分析プロセス（考古学フェーズ）** — ナラティブの考古学的根拠
  （初出コミット・AI 生成痕跡・PR レビュー・ADR-0019 参照）の元
- **§4.3 アクション生成（返済 PR）** — パイプラインの「計画 → 返済 → 検証」ステージの根拠
- **§6.1 ダッシュボード「今週の活動」** — 活動ログの集約との対比
- **§6.5 ナラティブ生成** — 一人称ナラティブの直接の要件（`UserService.ts` の例文）

### GitLab 参考実装（着想源 / 反面教師）

- `gitlab/app/assets/javascripts/ci/pipeline_details/graph/components/job_item.vue`
  — ステータスアイコン + 失敗時リトライ → 思考ステップ行 / パイプラインノードに転用
- `gitlab/app/assets/javascripts/ci/pipeline_details/graph/components/stage_column_component.vue`
  — ステージ名 + ノード縦積み → エージェント実行ステージ列に転用
- `gitlab/app/assets/javascripts/ci/pipeline_details/graph/components/linked_pipeline.vue`
  — ステージ列の依存リンク / 展開トグル → ステージ間リンクに転用
- `gitlab/app/assets/javascripts/repository/components/last_commit.vue`
  — CiIcon の GraphQL subscription / ポーリングによるライブ更新 → ライブステータスアイコンの着想
- **GitLab Duo（反面教師）** — 右下汎用チャットボットの受動的 Q&A を **採用しない**。
  Twin Agent は固有の居場所・人格・能動的活動ログを持つ

### 関連 issue

- **前提:** `app-shell-super-sidebar-foundation`（アプリシェル / Super Sidebar 基盤）
- issue-004（ADK エージェント基盤）— 将来、本ビューの実データ供給元になる想定
