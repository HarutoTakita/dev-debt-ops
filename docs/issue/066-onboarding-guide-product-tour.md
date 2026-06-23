# オンボーディングガイド（初回プロジェクト作成時のプロダクトツアー）を実装し、ダッシュボードの「はじめに」を置き換える

## 概要

ダッシュボード上部の「はじめに」セクション（理解度マップ/コード品質マップ/クイズ/リポジトリへ**遷移するだけ**のカード）は価値が低いため撤去する。代わりに、**初回プロジェクト作成時**に、各メニュー画面・操作・設定をハイライトしながら吹き出しで説明する**プロダクトツアー（オンボーディングガイド）**を実装する。ガイドはいつでも、**サイドバー左下の `?` アイコン → ヘルプページ**から再生できる。

## 背景・目的

- 「はじめに」カード（`getting-started.svelte`）は単なるリンク集で、製品の使い方（診断 → 返済ループ）を説明しない。
- リポジション（理解負債中心）後の UI は、初見では「何をどの順で見るか」が分かりにくい。能動的なツアーで初回体験を導く。
- ガイドは初回自動 + 任意再生（ヘルプ）で、いつでも復習できるようにする。

### 現状（撤去/変更対象）
- `frontend/src/lib/components/overview/getting-started.svelte`（カード本体）＋ `routes/[org]/[project]/+page.svelte` の `<GettingStarted />`（描画）。
- i18n: `getting_started_*`（ja/en）。
- `stores/project-store.svelte.ts` の `gettingStartedDismissed` / `dismissGettingStarted`（getting-started 専用の dismiss 永続）。
- アプリシェル: `routes/[org]/+layout.svelte`（Topbar + `SuperSidebar` + main）。サイドバー本体 `components/shell/super-sidebar.svelte`（最下部に「新規プロジェクト」ボタン）。
- 初回判定の足がかり: `routes/[org]/projects/new/+page.svelte` の `createProject` 成功直後。localStorage 永続の前例は `project-store` / `sidebar-store` / `recent-searches`。

## 設計

> 制約: SPA は外部ホストへ通信不可。ツアーは**外部 CDN/ライブラリに依存しない自作の軽量実装**（オーバーレイ + 吹き出し）。shadcn の Tooltip/Dialog は補助に使ってよいが、ハイライト切り抜きは自作。

### A. 「はじめに」セクションの撤去
- `<GettingStarted />` の描画と import を `[org]/[project]/+page.svelte` から削除。`getting-started.svelte` を削除。
- `getting_started_*` i18n と `project-store` の `gettingStartedDismissed`/`dismissGettingStarted` を削除（他参照が無いことを確認）。

### B. オンボーディング状態ストア（`stores/onboarding-store.svelte.ts`、新規）
- localStorage 永続（前例に倣い key `rosetta:onboarding`）。org ごとに完了フラグを保持。
- 状態: `active: boolean` / `stepIndex: number` / `completedByOrg: Record<string, boolean>` / `pendingStartOrg: string | null`（初回作成→遷移後に自動開始するためのワンショット）。
- メソッド: `requestAutoStart(orgSlug)`（初回作成時）/ `consumeAutoStart(orgSlug): boolean`（シェル mount 時に1回だけ true）/ `start()` / `next()` / `prev()` / `skip()` / `finish(orgSlug)`（完了フラグ保存）/ `isCompleted(orgSlug)`。

### C. ツアー定義（`components/onboarding/tour-steps.ts`、新規）
- ステップ配列。各ステップ: `{ id, target: string（data-tour 値）, titleKey, bodyKey, placement: "right"|"bottom"|..., route?: (ctx)=>Pathname }`。
- 対象（順序案）: ①サイドバーのプロジェクト/ナビ概観 → ②理解度マップ（nav-galaxy）→ ③コード品質マップ（nav-matrix）→ ④クイズと学習（nav-knowledge-hub）→ ⑤リポジトリ（nav-repos）→ ⑥設定（nav-settings）→ ⑦Overview の「解析」ボタン（最重要操作）→ ⑧ヘルプ `?`（あとで再生できる旨）。
- `route` 指定があるステップは、表示前に `goto` してターゲット出現を待つ（クロスページ・ハイライト）。

### D. ツアー・オーバーレイ（`components/onboarding/onboarding-tour.svelte`、新規）
- 全画面オーバーレイ: 背景 dim + **ターゲット要素の矩形を切り抜いてハイライト**（`getBoundingClientRect` で算出。box-shadow で外側を暗くする手法）。
- 吹き出し: ターゲット近傍に `title`/`body`/進捗（n/total）/「戻る・次へ・スキップ」。最終ステップは「完了」。
- ターゲット解決: `document.querySelector('[data-tour="<id>"]')`。`route` 指定時は `goto` → 短いポーリングで出現待ち（タイムアウトで次へフォールバック）。`resize`/`scroll` で位置再計算。
- a11y: Esc でスキップ、フォーカストラップ、`aria-live` で本文読み上げ、`prefers-reduced-motion` 配慮。
- アプリシェル `[org]/+layout.svelte` に `<OnboardingTour />` を常設し、mount 時 `consumeAutoStart` が true なら自動開始。

### E. ハイライト対象に `data-tour` 付与
- `components/shell/nav-item.svelte`（or `project-nav-group`）: 各ナビ項目に `data-tour={`nav-${item.id}`}`。
- `components/overview/analysis-run-cockpit.svelte`: 「解析」CTA に `data-tour="analysis-run"`。
- `super-sidebar.svelte`: ヘルプ `?` に `data-tour="help"`。
- 設定: `nav-settings`（ナビ項目で代替）。

### F. 初回トリガー（`routes/[org]/projects/new/+page.svelte`）
- `createProject` 成功時、**作成前に `project.list` が空＝初回**なら `onboarding.requestAutoStart(orgSlug)` を呼ぶ。遷移先のシェルで自動開始。

### G. ヘルプ `?` アイコン + ヘルプページ
- `super-sidebar.svelte` 最下部（新規プロジェクトの下）に `?` アイコンボタン（折りたたみ時は Tooltip、`data-tour="help"`）。クリックで `[org]/[project]/help` へ（プロジェクト選択時。未選択時は非活性 or org ヘルプ）。
- `routes/[org]/[project]/help/+page.svelte`（新規）: 「オンボーディングガイドを再生する」ボタン（`onboarding.start()`）＋ 各メニューの要点（診断 → 返済ループ）の簡単な説明リスト。

### H. i18n（ja/en）
- ステップの title/body、ヘルプページ文言、`?` ラベル、ツアー操作（次へ/戻る/スキップ/完了）。

## タスク

### frontend
- [ ] 「はじめに」撤去（`getting-started.svelte` 削除、`+page.svelte` から除去、i18n `getting_started_*` 削除、`project-store` の dismiss ロジック削除）。
- [ ] `stores/onboarding-store.svelte.ts` 新規（localStorage 永続・自動開始ワンショット・ステップ進行）。
- [ ] `components/onboarding/tour-steps.ts` 新規（ステップ定義）。
- [ ] `components/onboarding/onboarding-tour.svelte` 新規（オーバーレイ + 吹き出し + ターゲット解決 + クロスページ goto + a11y）。Map/Set を使う計算は `.ts` に切り出し（eslint `prefer-svelte-reactivity`）。
- [ ] 対象要素へ `data-tour` 付与（nav-item / analysis-run-cockpit / super-sidebar help）。
- [ ] `[org]/+layout.svelte` に `<OnboardingTour />` 常設 + 自動開始配線。
- [ ] `projects/new/+page.svelte` の初回判定 → `requestAutoStart`。
- [ ] `super-sidebar.svelte` に `?` ヘルプアイコン、`[org]/[project]/help/+page.svelte` 新規（再生ボタン + 説明）。
- [ ] i18n（ja/en）追加。

### test（vitest）
- [ ] onboarding-store: 自動開始ワンショット（consume は 1 回のみ true）、完了フラグ永続、ステップ進行。
- [ ] ツアー: ステップ前進/後退/スキップ、`data-tour` 解決、未存在ターゲットのフォールバック。
- [ ] 初回のみ自動開始（2 個目のプロジェクト作成では起動しない）。

## 完了条件
- ダッシュボードの「はじめに」カードが無くなる。
- 初回プロジェクト作成後、各メニュー・操作・設定をハイライト + 吹き出しで案内するツアーが自動で始まり、スキップ/完了でき、完了状態が永続する（再ログイン後に再自動表示しない）。
- サイドバー左下の `?` → ヘルプページから、いつでもガイドを再生できる。
- 外部 CDN/通信に依存しない（SPA 自己完結）。
- フロント: `bun run check`（警告ゼロ）/ `lint` / `test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Added`（オンボーディングガイド）/ `Removed`（はじめにカード）を追記。

## 対象外・保留
- 役割別（PM/開発者）のツアー出し分け、多段チュートリアル動画。
- バックエンドでの onboarding 状態保存（本 issue は localStorage 永続のみ）。
- ツアーの自動翻訳以外の高度な国際化。

## 参考
- 撤去: `frontend/src/lib/components/overview/getting-started.svelte` / `routes/[org]/[project]/+page.svelte` / `stores/project-store.svelte.ts`（dismiss）/ `messages/{ja,en}.json`（`getting_started_*`）。
- シェル: `routes/[org]/+layout.svelte` / `components/shell/super-sidebar.svelte` / `project-nav-group.svelte` / `nav-item.svelte` / `config/nav.ts`。
- 作成フロー: `routes/[org]/projects/new/+page.svelte` / `lib/api/client.ts`（`createProject`）/ `stores/project-store.svelte.ts`（`list`/`loadList`）。
- 永続の前例: `stores/{project-store,sidebar-store,recent-searches}.svelte.ts`（localStorage）。
- UI プリミティブ: `components/ui/{tooltip,dialog,popover,button}`。
- 規約: `CLAUDE.md`（Svelte 5 runes・shadcn `ui/` 読取専用・外部通信不可（自己完結）・i18n ja/en・kebab-case・CHANGELOG 日本語・ゲート）。
