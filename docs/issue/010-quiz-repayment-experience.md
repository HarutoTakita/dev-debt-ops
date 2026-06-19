# クイズ返済体験を実装する（集中モード + 建設的結果 + 学習プラン遷移 / Coming Soon プレースホルダ）

## 概要

仕様書 §6.4「クイズ UI」を、Rosetta の**返済の瞬間（Re:Pay）**として実装する。
ナレッジ負債を「クイズ合格で Knowledge Coverage (KC) が上がる」というゲーミフィケーション体験に落とし込み、

1. `[org]/quizzes` に受験可能クイズ一覧（サイドバー pill = 件数）
2. **集中モード**受験画面（コードスニペット表示 + 解答入力 + 途中保存）
3. **建設的フレーミング**の結果画面（「正解/不正解」でなく「あなたが理解していたこと / 学ぶ余地」、KC が 23%→47% へ上がる会計的演出）
4. 結果から学習プランへの滑らかな遷移

を提供する。

ただし本 issue は **coming-soon カテゴリ** であり、**機能本体（受験ロジック・採点・実 API）は実装しない**。
**ナビ枠・ルート・Coming Soon プレースホルダ（場所だけ）と、`QuizSession` 系の Zod スキーマ + モックデータ**を用意し、後続 issue が中身を差し込めるようにすることがゴールである。

## 背景・目的

GitLab では技術負債の返済は最終的に「MR（PR）マージ」という事務的なイベントに収束する。Rosetta はそこを差別化する。
**負債返済を、クイズに合格して KC スコアが上がる体験として演出する**（仕様書 §1「クイズに合格して、負債を返済する」、§5.2「クイズによる確証」）。
結果画面は減点採点（◯×・スコア羅列）を避け、**「あなたが理解していたこと」と「学ぶ余地」**という建設的フレーミングで提示し、KC が `23% → 47%` へ繰り上がる瞬間を**会計帳簿のカウントアップアニメーション**で見せる。これが Re:Pay（返済）の含意である。

この体験は GitLab には存在しない Rosetta 固有領域であり、UI クローン臭の心配が最も少ない。GitLab の資産は**部品としてのみ**借りる:

- 受験前の空状態 → Pajamas `EmptyStateComponent`（`gl-empty-state` レイアウト）の構造を参考に、Rosetta ブランドの独自プレースホルダを作る
- 途中保存・採点中などの**ステータス表現** → `ci_icon.vue` の `status` オブジェクト駆動パターン（`{ icon, text, variant }`）を参考にする
- 結果画面の本文 + メタ情報の骨格 → 詳細ビュー（`last_commit.vue` 等）のヘッダ + 本文構成を参考にする

これらは「設計の借用」であって、見た目・コピー・演出はすべて Rosetta 独自で作る。

### 前提 Issue

- **app-shell-super-sidebar-foundation**（アプリシェル / Super Sidebar 基盤）— 本 issue のクイズ一覧 pill はこのサイドバーのナビ項目に配線する。サイドバー基盤が未完の場合、`[org]/+layout.svelte` の暫定ヘッダ内に仮ナビリンクを置き、基盤完成後に pill を移設する。

## タスク

### スキーマ / モック（`frontend/src/lib/api/schemas.ts`）

- [ ] `quizQuestionSchema` を追加する（`id` / `kind`（multiple_choice | free_text）/ `prompt` / `code_snippet`（`{ language, path, content }`）/ `choices?` / `difficulty`（L1-L5））
- [ ] `quizAnswerSchema` を追加する（`question_id` / `value`（選択肢 ID または自由記述）/ `saved_at`）
- [ ] `quizSessionSchema` を追加する（仕様書 §7.1 の `QuizSession` に対応: `id` / `developer_id` / `file` / `questions` / `answers` / `status`（not_started | in_progress | grading | completed）/ `started_at` / `completed_at` / `score`）
- [ ] `quizResultSchema` を追加する（建設的結果用: `understood`（理解していたこと: `Concept[]`）/ `gap_concepts`（学ぶ余地: `Concept[]`）/ `kc_before` / `kc_after`（例 0.23 → 0.47）/ `learning_plan_id`）
- [ ] `quizListItemSchema` / `quizListSchema` を追加する（受験可能一覧: `session_id` / `file_path` / `repo_full_name` / `reason`（仕様書 §5.1 の KC 低下理由）/ `question_count` / `estimated_minutes`）
- [ ] 上記すべてに `z.infer` の型エクスポートを追加する
- [ ] `frontend/src/lib/api/quiz-mock.ts` を新規作成し、`UserService.ts`（仕様書 §6.5 のナラティブ例に対応）を題材にした受験可能 2〜3 件・5 問構成（L1-L5）のモック `QuizSession` と、`kc_before: 0.23 / kc_after: 0.47` の `QuizResult` モックを定義する

### API クライアント（`frontend/src/lib/api/client.ts`）— モック配線のみ

- [ ] `listQuizzes(orgSlug)` / `getQuizSession(sessionId)` / `saveQuizAnswer(sessionId, answer)`（PATCH 想定）/ `submitQuiz(sessionId)` を**シグネチャだけ**定義し、内部は `quiz-mock.ts` を返す（`// TODO: 実 API 接続は後続 issue` コメントを付ける）
- [ ] 既存 `apiFetch` パターンに合わせ、レスポンスを `quiz*Schema.parse(...)` で検証する形（モックも `parse` を通す）にしておく

### ストア（`frontend/src/lib/stores/quiz-store.svelte.ts`）

- [ ] Svelte 5 クラスベース runes パターンで `QuizStore` を新規作成する
  - `availableCount = $state<number>(0)`（サイドバー pill 用）
  - `current = $state<QuizSession | null>(null)`（受験中セッション）
  - `draftAnswers = $state<Record<string, QuizAnswer>>({})`（途中保存ドラフト）
  - `saveStatus = $state<"idle" | "saving" | "saved">("idle")`（`ci_icon` 風ステータス表現）
  - メソッド: `loadAvailable(orgSlug)` / `start(sessionId)` / `saveDraft(answer)` / `reset()`

### ルート / ナビ枠（Coming Soon）

- [ ] `frontend/src/routes/[org]/quizzes/+page.svelte` を新規作成する（受験可能一覧 + 受験前は **ComingSoonPlaceholder**）
- [ ] `frontend/src/routes/[org]/quizzes/[sessionId]/+page.svelte` を新規作成する（集中モード受験画面の枠 + プレースホルダ）
- [ ] `frontend/src/routes/[org]/quizzes/[sessionId]/result/+page.svelte` を新規作成する（建設的結果画面の枠 + プレースホルダ）
- [ ] Super Sidebar 基盤（前提 issue）のナビに「クイズ」項目を追加し、`quiz.availableCount > 0` のとき **pill（件数バッジ）** を表示する配線を入れる（基盤未完なら `[org]/+layout.svelte` に仮リンク）

### コンポーネント（`frontend/src/lib/components/quiz/`）

- [ ] `coming-soon-placeholder.svelte` — 場所だけ用意する汎用 Coming Soon プレースホルダ（Rosetta ブランド表現、props: `title` / `description` / `eyebrow?`）
- [ ] `quiz-list.svelte` — 受験可能一覧（カード: ファイルパス・KC 低下理由・問題数・推定分）
- [ ] `focus-mode.svelte` — 集中モードのシェル（最小限の chrome、進捗インジケータ、途中保存ステータス）
- [ ] `code-snippet-panel.svelte` — コードスニペット表示（既存 `repo/file-viewer.svelte` の表示方針に合わせる）
- [ ] `answer-input.svelte` — 解答入力（選択肢 / 自由記述を `kind` で出し分け、入力ごとに `saveDraft` を呼ぶ）
- [ ] `constructive-result.svelte` — 建設的結果（「あなたが理解していたこと」「学ぶ余地」の 2 カラム + KC カウントアップ演出 + 学習プラン遷移 CTA）
- [ ] `kc-meter.svelte` — KC スコアの 23%→47% カウントアップ / バー伸長アニメーション

### i18n（Paraglide）

- [ ] `messages/ja.json` / `messages/en.json` にクイズ関連メッセージを追加する（一覧・集中モード・結果・Coming Soon・「あなたが理解していたこと」「学ぶ余地」等）。日本語をプライマリとする

## 完了条件

- **本 issue では機能本体（実受験・実採点・実 API）は実装しない** — ナビ枠・3 ルート・Coming Soon プレースホルダ（場所だけ）が用意されていること
- `[org]/quizzes` にアクセスでき、受験前は **ComingSoonPlaceholder**（Rosetta ブランド表現）が表示されること
- `quiz-mock.ts` の `QuizSession` / `QuizResult` モックが対応する Zod スキーマ（`quizSessionSchema` / `quizResultSchema`）を `parse` で通過すること
- 受験可能件数が 1 件以上のとき、サイドバー（または仮ナビ）に **pill（件数）** が表示されること（モック値で可）
- `[org]/quizzes/[sessionId]` で集中モードのレイアウト枠（スニペット領域 + 解答領域 + 途中保存ステータス表示）が確認できること（モックデータ表示で可）
- `[org]/quizzes/[sessionId]/result` で建設的結果の枠が表示され、**KC 23% → 47% のカウントアップ演出**が再生され、学習プランへの遷移 CTA が存在すること
- `bun run check`（svelte-check）と `bun run lint`（prettier + eslint）がパスすること

## 技術詳細

### 画面遷移

```
[org]/quizzes
  └─（一覧カードをクリック）→ [org]/quizzes/[sessionId]   （集中モード受験）
        └─（提出 submit / 採点中 grading）→ [org]/quizzes/[sessionId]/result
              └─（学習プランへ CTA）→ [org]/learning-plans/[planId]  （後続 issue）
```

### 画面レイアウト: 受験可能一覧（`[org]/quizzes/+page.svelte`）

```
┌────────────────────────────────────────────────┐
│ クイズ — 返済を待っているナレッジ負債      [pill 2]│
├────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────┐   │
│ │ src/services/user-service.ts               │  │
│ │ 理由: AI 生成 + レビューが形式的            │  │
│ │ 5 問 (L1-L5) · 約 8 分        [受験する →]   │  │
│ └──────────────────────────────────────────┘   │
│ ┌──────────────────────────────────────────┐   │
│ │ src/auth/token-rotation.ts                  │  │
│ │ 理由: 作者が離脱 · KC 0.31                   │  │
│ │ 5 問 (L1-L5) · 約 6 分        [受験する →]   │  │
│ └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────┘
（受験前 / モック未投入時は ComingSoonPlaceholder を全面表示）
```

### 画面レイアウト: 集中モード（`[org]/quizzes/[sessionId]/+page.svelte`）

最小限の chrome（既存 `[org]/+layout.svelte` のヘッダは出さず没入させる）。
左にコードスニペット、右に解答。下部に進捗と**途中保存ステータス**。

```
┌──────────────── 問 2 / 5 ──── ● 保存済み 14:03 ── [中断] ─┐
├─────────────────────────────┬───────────────────────────┤
│ code-snippet-panel          │ answer-input              │
│ // src/services/user-service│ Q. この関数が ADR-0019 に  │
│ async function merge(...) {  │    違反する理由は?         │
│   // AI 生成の重複ロジック    │ ○ 重複した検証ロジック     │
│   ...                        │ ○ 同期 I/O                 │
│ }                            │ ◉ 単一責任の逸脱           │
│                              │ [ ← 前へ ]      [ 次へ → ] │
└─────────────────────────────┴───────────────────────────┘
```

途中保存ステータスは `ci_icon.vue` の status オブジェクト駆動を参考に、Rosetta 独自表現にする:

```
idle   → （非表示）
saving → ◌ 保存中…
saved  → ● 保存済み HH:MM
```

### 画面レイアウト: 建設的結果（`[org]/quizzes/[sessionId]/result/+page.svelte`）

「正解/不正解」を出さない。`understood` と `gap_concepts` の 2 カラム + KC カウントアップ。

```
┌────────────────────────────────────────────────┐
│  返済完了 — Knowledge Coverage を更新しました     │
│                                                  │
│        KC   23% ━━━━━▶ 47%   (+24pt)             │
│        [■■■■■□□□□□]  ← バーが伸びる演出           │
│                                                  │
├──────────────────────┬───────────────────────────┤
│ あなたが理解していたこと │ 学ぶ余地                   │
│ ・トークンローテーション │ ・再利用検出の不変条件      │
│ ・JWT 有効期限の意図     │ ・冪等性とリトライ          │
├──────────────────────┴───────────────────────────┤
│              [ 学習プランへ進む → ]                 │
└────────────────────────────────────────────────┘
```

### コンポーネント構成

```
routes/[org]/quizzes/+page.svelte
  └─ quiz-list.svelte                 （または coming-soon-placeholder.svelte）

routes/[org]/quizzes/[sessionId]/+page.svelte
  └─ focus-mode.svelte
        ├─ code-snippet-panel.svelte
        └─ answer-input.svelte

routes/[org]/quizzes/[sessionId]/result/+page.svelte
  └─ constructive-result.svelte
        └─ kc-meter.svelte

lib/stores/quiz-store.svelte.ts        （availableCount → サイドバー pill）
lib/api/quiz-mock.ts                    （QuizSession / QuizResult モック）
```

### Coming Soon プレースホルダの見た目（`coming-soon-placeholder.svelte`）

GitLab Pajamas `EmptyStateComponent`（`gl-empty-state`: 中央寄せ縦並び、見出し + 説明 + ボタン）の**構造**を借りつつ、見た目は Rosetta ブランド独自にする。

```
┌────────────────────────────────────────────────┐
│                                                  │
│                  ◎  Re:Pay                       │  ← eyebrow（小さいラベル）
│                                                  │
│           クイズ返済はまもなく登場します           │  ← title
│                                                  │
│   ナレッジ負債をクイズで返済し、KC を引き上げる    │  ← description
│   体験を準備中です。                              │
│                                                  │
│            [ 仕様を見る ]（任意）                  │
│                                                  │
└────────────────────────────────────────────────┘
```

props（kebab-case ファイル / camelCase props）:

```svelte
<script lang="ts">
  type Props = { title: string; description: string; eyebrow?: string };
  const { title, description, eyebrow }: Props = $props();
</script>
```

### Zod スキーマ（`frontend/src/lib/api/schemas.ts` に追記）

仕様書 §7.1 の `QuizSession` / `LearningPlan` に対応。snake_case はそのまま保持（既存方針）。

```typescript
// Quiz
export const conceptSchema = z.object({ id: z.string(), label: z.string() });

export const quizQuestionSchema = z.object({
  id: z.string(),
  kind: z.enum(["multiple_choice", "free_text"]),
  prompt: z.string(),
  code_snippet: z.object({ language: z.string(), path: z.string(), content: z.string() }).nullable(),
  choices: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  difficulty: z.enum(["L1", "L2", "L3", "L4", "L5"]),
});

export const quizAnswerSchema = z.object({
  question_id: z.string(),
  value: z.string(),
  saved_at: z.iso.datetime({ offset: true }),
});

export const quizSessionSchema = z.object({
  id: z.string(),
  developer_id: z.string(),
  file: z.object({ path: z.string(), repo_full_name: z.string() }),
  questions: z.array(quizQuestionSchema),
  answers: z.array(quizAnswerSchema),
  status: z.enum(["not_started", "in_progress", "grading", "completed"]),
  started_at: z.iso.datetime({ offset: true }).nullable(),
  completed_at: z.iso.datetime({ offset: true }).nullable(),
  score: z.number().nullable(),
});

export const quizResultSchema = z.object({
  session_id: z.string(),
  understood: z.array(conceptSchema), // あなたが理解していたこと
  gap_concepts: z.array(conceptSchema), // 学ぶ余地
  kc_before: z.number(), // 例: 0.23
  kc_after: z.number(), // 例: 0.47
  learning_plan_id: z.string().nullable(),
});

export const quizListItemSchema = z.object({
  session_id: z.string(),
  file_path: z.string(),
  repo_full_name: z.string(),
  reason: z.string(), // KC が低い理由（§5.1）
  question_count: z.number(),
  estimated_minutes: z.number(),
});
export const quizListSchema = z.object({ quizzes: z.array(quizListItemSchema) });

export type Concept = z.infer<typeof conceptSchema>;
export type QuizQuestion = z.infer<typeof quizQuestionSchema>;
export type QuizAnswer = z.infer<typeof quizAnswerSchema>;
export type QuizSession = z.infer<typeof quizSessionSchema>;
export type QuizResult = z.infer<typeof quizResultSchema>;
export type QuizListItem = z.infer<typeof quizListItemSchema>;
export type QuizList = z.infer<typeof quizListSchema>;
```

### ストア設計（`frontend/src/lib/stores/quiz-store.svelte.ts`）

既存 `repo-store.svelte.ts` と同じ Svelte 5 クラスベース runes パターン。

```typescript
import type { QuizAnswer, QuizSession } from "$lib/api/schemas";

class QuizStore {
  availableCount = $state<number>(0); // サイドバー pill
  current = $state<QuizSession | null>(null);
  draftAnswers = $state<Record<string, QuizAnswer>>({});
  saveStatus = $state<"idle" | "saving" | "saved">("idle");

  saveDraft(answer: QuizAnswer) {
    this.saveStatus = "saving";
    this.draftAnswers = { ...this.draftAnswers, [answer.question_id]: answer };
    // TODO: 実 API は後続 issue。今は楽観的に保存済みへ
    this.saveStatus = "saved";
  }

  reset() {
    this.current = null;
    this.draftAnswers = {};
    this.saveStatus = "idle";
  }
}

export const quiz = new QuizStore();
```

### KC カウントアップ演出（`kc-meter.svelte`）

`kc_before → kc_after` を Svelte の `Tween`（`svelte/motion`）で補間し、パーセント数値とバー幅を同時にアニメーションさせる。会計帳簿が繰り上がるニュアンス（Re:Pay）を出す。

```svelte
<script lang="ts">
  import { Tween } from "svelte/motion";
  import { cubicOut } from "svelte/easing";

  type Props = { before: number; after: number };
  const { before, after }: Props = $props();

  const pct = new Tween(before * 100, { duration: 1200, easing: cubicOut });
  $effect(() => {
    pct.target = after * 100;
  });
</script>

<div class="flex items-center gap-3">
  <span class="tabular-nums text-2xl font-semibold">{Math.round(pct.current)}%</span>
  <div class="h-2 flex-1 overflow-hidden rounded bg-muted">
    <div class="h-full bg-primary transition-none" style="width: {pct.current}%"></div>
  </div>
  <span class="text-sm text-primary">+{Math.round((after - before) * 100)}pt</span>
</div>
```

### サイドバー pill 配線

前提 issue（app-shell-super-sidebar-foundation）のナビ項目に件数バッジを表示する。
GitLab `nav_item.vue` の `pill_count` パターン（数値 or 非空文字列のときだけ表示）を参考に、`quiz.availableCount > 0` を条件にする。

```svelte
{#if quiz.availableCount > 0}
  <span class="ml-auto rounded-full bg-primary/10 px-2 text-xs text-primary">{quiz.availableCount}</span>
{/if}
```

## 参考

### 仕様書

- `仕様書.md` §6.4「クイズ UI」（集中モード / 建設的フレーミング / 学習プラン遷移）— 本 issue の主要根拠
- `仕様書.md` §1「クイズに合格して、負債を返済する」、§0「クイズ合格で負債返済」という体験価値
- `仕様書.md` §5.1「Knowledge Coverage (KC) の算出」（受験対象の選定理由 / KC スコア）
- `仕様書.md` §5.2「クイズ生成プロセス」「クイズ難易度設計（L1-L5）」
- `仕様書.md` §5.3「ギャップ概念の抽出」（結果画面の「学ぶ余地」の入力）
- `仕様書.md` §5.4「学習プラン生成」（結果からの遷移先）
- `仕様書.md` §6.5「ナラティブ生成」（`UserService.ts` の例題をモックに採用）
- `仕様書.md` §7.1「主要エンティティ」`QuizSession` / `LearningPlan` / `Concept` / `Resource`（Zod スキーマの対応元）

### 現行フロントエンド（合わせる対象）

- `frontend/src/routes/[org]/+page.svelte` — ルート配下のページ構成・`$effect` パターン
- `frontend/src/routes/[org]/+layout.svelte` — 暫定ヘッダ（サイドバー基盤未完時の仮ナビ置き場）
- `frontend/src/lib/stores/repo-store.svelte.ts` — Svelte 5 クラスベース runes ストアの雛形
- `frontend/src/lib/components/repo/file-viewer.svelte` — コードスニペット表示の方針
- `frontend/src/lib/components/repo/tech-stack-panel.svelte` — パネル状態管理（idle/loading/done/error）と pill 風バッジ表現
- `frontend/src/lib/api/schemas.ts` / `frontend/src/lib/api/client.ts` — Zod スキーマ追記先 / API クライアント `apiFetch` パターン

### GitLab 参考実装（部品としての借用元）

- `gitlab/app/components/pajamas/empty_state_component.html.haml` — 受験前の空状態（`gl-empty-state` レイアウト）の構造参考 → ComingSoonPlaceholder
- `gitlab/app/assets/javascripts/vue_shared/components/ci_icon/ci_icon.vue` — status オブジェクト駆動（`{ icon, text, variant }`）の途中保存/採点中ステータス表現
- `gitlab/app/assets/javascripts/repository/components/last_commit.vue` — 詳細ビュー（ヘッダ + 本文 + メタ）の骨格 → 結果画面
- `gitlab/app/assets/javascripts/super_sidebar/components/nav_item.vue` — `pill_count` 表示パターン → サイドバー件数 pill
