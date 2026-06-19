# 隠れた逸品の表出化・オンボーディング・解析ライフサイクル

## 概要

「最初の 30 秒」を導くための 3 つの UX 改善を 1 本にまとめる。
(1) 開発者向けの隠れたプレビュー導線（`underline` テキストリンク）を一級の primary action に昇格し、
本番ビルドからは dev 文言を除去する。(2) Overview 上部に閉じられる「はじめに」アクションカードを置き、
Galaxy / Matrix / Quiz / Repos への最初の一歩を提示する。(3) リポジトリ接続直後に
`overviewMock` を実データのように即時描画してしまう問題を解消し、解析ライフサイクル
（スキャン進行中 → 完了）を観測可能にする（最低でも「Sample/デモデータ」バッジ）。
いずれも **バックエンド不要**（フロントのみ）。

## 背景・目的

横断テーマは **「隠れた逸品を表に出して最初の 30 秒を導く」** と
**「観察可能な解析ライフサイクル（偽データを本物に見せない）」** の 2 つである。

現状の Coming Soon 系プレースホルダには、プロダクトの世界観を伝える良質なプレビュー
（モックの星域・クイズ一覧・観測台ダッシュボード）が仕込まれているが、その入口が
`text-xs ... underline` の **開発者向けテキストリンク**でしか露出していない。
これは「隠れた逸品」であり、初見ユーザーの目に留まらないどころか、本番でも
`（開発用）…` という dev 文言がそのまま表示されてしまう。

加えて、初見ユーザーが org → project に入った直後、何から触ればよいかの導線が無い
（Overview にオンボーディングが存在しない）。さらに最も重い問題として、
リポジトリを接続した瞬間に **完成済みダッシュボード（モックデータ）** が
実データであるかのように描画され、「解析がいつ走り、いつ結果が出るのか」という
ライフサイクルが UI から完全に消えている。これは偽データを本物に見せる UX 上の
重大な不誠実であり、デモでも「もう解析済みなのか？」という誤解を生む。

本 issue はこれら 3 点を、既存の Coming Soon プレースホルダ・ぼかしプレビュー構図・
`project-store` の localStorage 永続パターンを流用して解消する。

## タスク

### rank 2a — 隠れたプレビューを primary action に昇格 + 本番から dev 文言を除去 [重大/S]

クイズと Galaxy の双方で、`underline` の dev テキストリンクを一級の primary action
（「デモを見る / Preview」）へ差し替える。本番ビルドでは dev 文言・dev 導線を表示しない。

> 注（レビュー指摘の補正）: レビューは「Galaxy には経路自体が無い」としていたが不正確。
> Galaxy 側は `frontend/src/lib/components/galaxy/coming-soon-placeholder.svelte:26-32` に
> 既に `galaxy.loadMock()` の dev underline リンクと `startScan()` の primary Button が存在する。
> 真の問題は「dev リンクでしかプレビューに入れない」「本番で dev 文言が露出する」点であり、
> その本体は有効。なお Galaxy の placeholder は quiz とは**別の自作コンポーネント**で、
> `action` snippet 非対応・`Button` 直書きである点に注意（quiz の placeholder は汎用 Snippet 対応）。

- [ ] クイズ: `frontend/src/routes/[org]/[project]/quizzes/+page.svelte:18-26` の
      `action` snippet 内の dev テキストリンク（`<button class="text-xs ... underline" onclick={() => quiz.loadAvailable(orgSlug)}>{m.quiz_coming_preview()}</button>`）を
      shadcn-svelte の primary `Button`（「デモを見る / Preview」）に差し替える。
      差し替え先の汎用 placeholder は `frontend/src/lib/components/quiz/coming-soon-placeholder.svelte:5`
      が `title/description/eyebrow/action` の Snippet を受けるため、`action` snippet 内の Button 置換のみで済む。
- [ ] Galaxy: `frontend/src/lib/components/galaxy/coming-soon-placeholder.svelte:26-32` の
      dev underline リンク（`onclick={() => galaxy.loadMock()}` / `m.galaxy_coming_preview()`）を、
      既存の `startScan()` 主 Button（`galaxy_coming_cta`）と並ぶ **secondary な「デモを見る / Preview」Button**
      に昇格する（自作コンポーネントのため `Button` を直書きで差し替え。`variant="outline"` 等で主従を付ける）。
- [ ] 本番での dev 文言・dev 導線を除去する。dev プレビュー（`quiz.loadAvailable` / `galaxy.loadMock`）を
      開発時のみ表示するため `import.meta.env.DEV` でガードするか、本番向けに
      「デモを見る / Preview」文言（dev 色を取り除いた新メッセージキー）へ置き換える。
      旧キー `quiz_coming_preview`（`messages/ja.json:244` `（開発用）モックで一覧を読み込む` /
      `en.json:244` `(dev) Load the list with mock data`）と
      `galaxy_coming_preview`（`ja.json:236` `（開発用）モックで星域をプレビュー` /
      `en.json:236` `(dev) Preview the galaxy with mock data`）は本番表示には使わない。
- [ ] Paraglide 2.0 で新メッセージキー（例: `quiz_coming_demo` / `galaxy_coming_demo` =「デモを見る」/「Preview」）を
      `frontend/messages/ja.json`（主）・`en.json`（従）に追加し、`frontend/src/lib/paraglide/messages` を再生成する。
- [ ] kebab-case ファイル命名・`ui/` 配下プリミティブの読み取り専用規約を維持
      （`Button` は `$lib/components/ui/button` を import して使い、`ui/` 外で合成する）。

### rank 6 — getting-started アクションカード [重大/M]

Overview 上部に、閉じられる「はじめに」グリッド（2〜4 枚）を新設する。
各カードは絵文字 + 一行説明 + href で、Galaxy / Matrix / Quiz / Repos への最初の一歩を提示する。
閉じた状態は localStorage に永続させる。**完全に未着手**（既存実装・コンポーネント・メッセージキーは皆無）。

> 検証: `frontend/src/` 全域を grep（getting-started / getting_started / はじめに）したが該当なし。
> Overview の `frontend/src/routes/[org]/[project]/+page.svelte` と
> `frontend/src/lib/components/overview/overview-dashboard.svelte` にもオンボーディング枠は存在しない
> （dashboard は DebtMatrix / StatCard / PriorityList 等のみ）。
> リンク先ルートは `frontend/src/routes/[org]/[project]/` 配下に galaxy / matrix / quizzes / repos が**全て実在**。

- [ ] `frontend/src/lib/components/overview/getting-started.svelte` を新設する
      （閉じられるカードグリッド。Svelte 5 runes・kebab-case）。
- [ ] カードは絵文字 + 一行説明 + href の 2〜4 枚。href は `resolve()` で
      `/${orgSlug}/${projectSlug}/galaxy` `/matrix` `/quizzes` `/repos` を生成する
      （`frontend/src/routes/[org]/[project]/+page.svelte:3` が既に `resolve` を import 済み — 同パターンを流用）。
- [ ] `frontend/src/routes/[org]/[project]/+page.svelte` の Overview 上部
      （`OverviewDashboard` の上 / `:24` の `{#if overview}` ブロック内冒頭）に getting-started を差し込む。
- [ ] 閉じる操作と「閉じた」状態の **localStorage 永続**を実装する。
      永続パターンは `frontend/src/lib/stores/project-store.svelte.ts:22-31,51-57`
      （`RECENT_KEY` の `localStorage.getItem` / `setItem` 読み書き）を踏襲する。
      ただし project-store には「閉じた」状態フィールドが無いため、
      新規フィールド（例: org 別 or project 別の `gettingStartedDismissed`）を **新規追加**する
      （`localStorage` ガードの `typeof localStorage !== "undefined"` も踏襲）。
- [ ] Paraglide 2.0 で多言語化。`frontend/messages/ja.json`（主）・`en.json`（従）に
      タイトル・各カード文言・「閉じる」ラベル等の新規キーを追加し `frontend/src/lib/paraglide/messages` を再生成する。

### rank 7 — 観察可能な解析ライフサイクル（偽データを本物に見せない）[重大/M]

リポジトリ接続後に `overviewMock` を実データとして即時表示してしまう問題を解消する。
最低限「Sample/デモデータ」バッジ、本格対応はスキャン進行中の中間状態
（ぼかしプレビュー + 不確定バー + 「スキャン開始」CTA、遅延後に `OverviewDashboard`）を導入する。

> 検証: `frontend/src/routes/[org]/[project]/+page.svelte:14-17` のコメントに
> 「プロジェクト内ではリポジトリが常に束縛されるため観測台（overviewMock）を描画する」と明記され、
> `const overview = $derived(repo.connected ? overviewMock : null)`（:17）。
> `frontend/src/lib/stores/repo-store.svelte.ts:4` の `connected` は `connect()` で常に truthy 化されるため、
> 接続直後に `overviewMock` が実データのように即時表示される。
> `frontend/src/lib/components/overview/overview-dashboard.svelte` には Sample バッジも中間状態も無い。
> ぼかしプレビュー機構自体は
> `frontend/src/lib/components/overview/coming-soon-placeholder.svelte:12-17`
> （`opacity-40 blur-[1px]` の preview snippet）に存在するが、現状は repo **未接続時のみ**で、
> 接続後のスキャン進行表現には使われていない。
> なおレビューの `+page.svelte:28-30` は未接続時用の preview snippet 箇所であり、問題の中核は :17 の派生式。

- [ ] **最低限対応（Sample/デモデータ バッジ）:**
      `frontend/src/lib/components/overview/overview-dashboard.svelte` に、表示中のダッシュボードが
      モック由来である間「Sample / デモデータ」バッジを表示する（実データ配線までの誠実表示）。
      バッジ表示有無を制御する prop（例: `isSample: boolean`）を受け取る形にする。
- [ ] **本格対応（スキャン進行中の中間状態）:**
      `frontend/src/lib/stores/repo-store.svelte.ts` にスキャン進行状態を表すフラグを **新規追加**する
      （現状 `connected` / `selectedBranch` のみでスキャン状態を持たないため。
      例: `scanState: "idle" | "scanning" | "done"`）。
- [ ] `frontend/src/routes/[org]/[project]/+page.svelte:17` の
      `repo.connected ? overviewMock : null` を、スキャン状態を踏まえた分岐に置き換える
      （接続直後 = スキャン進行中の中間状態を出し、完了後に `OverviewDashboard` へ遷移）。
- [ ] スキャン進行中の表現（ぼかしプレビュー + 不確定バー + 「スキャン開始」CTA）を実装する。
      ぼかしプレビュー構図は
      `frontend/src/lib/components/overview/coming-soon-placeholder.svelte:12-17` の
      `opacity-40 blur-[1px]` preview snippet を流用する（`overviewMock` を背後に透かす）。
      不確定バーは shadcn-svelte のプリミティブ（未導入なら `bunx shadcn-svelte@latest add progress`）か、
      Tailwind v4 のアニメーションで実装する。
- [ ] Paraglide 2.0 で「Sample/デモデータ」「スキャン開始」「スキャン中…」等の文言を
      `frontend/messages/ja.json`（主）・`en.json`（従）に追加し再生成する。

## 完了条件

- クイズ・Galaxy の Coming Soon で、プレビュー導線が `underline` テキストリンクではなく
  一級の Button（「デモを見る / Preview」）として表示され、押下で従来どおりモックプレビューに入れること。
- 本番ビルド（`bun run build`）で `（開発用）…` / `(dev) …` の dev 文言・dev 導線が一切表示されないこと。
- Overview 上部に「はじめに」アクションカード（2〜4 枚、絵文字 + 一行 + href）が表示され、
  各カードから Galaxy / Matrix / Quiz / Repos へ遷移できること。
- 「はじめに」を閉じるとカードが消え、リロード後も閉じたまま（localStorage 永続）であること。
- リポジトリ接続直後に完成済みダッシュボードが即時表示されず、スキャン進行中の中間状態
  （ぼかしプレビュー + 不確定バー + 「スキャン開始」CTA）を経て `OverviewDashboard` に遷移すること
  （最低でもモック由来の間は「Sample / デモデータ」バッジが出ること）。
- 追加・変更した文言が ja（主）・en（従）双方に存在し、Paraglide メッセージが再生成済みであること。
- バックエンド変更が無いこと（**バックエンド不要**）。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通ること。

## 対象外・保留

- なし（束ねた 3 指摘 rank 2a / 6 / 7 はいずれも実コード検証で `valid=true` /
  `alreadyImplemented=false` を確認済みで、全てタスク化した）。
  - rank 2a のレビュー文「Galaxy には経路自体が無い」は**事実誤認**だったため、
    タスク本文で補正のうえ「dev リンクを primary に昇格 + 本番から dev 文言除去」という
    指摘本体（有効）として取り込んだ（指摘自体は drop していない）。

## 参考

- 元レビュー rank 対応
  - rank 2a → 「rank 2a — 隠れたプレビューを primary action に昇格」節
  - rank 6 → 「rank 6 — getting-started アクションカード」節
  - rank 7 → 「rank 7 — 観察可能な解析ライフサイクル」節
- 関連ファイル（改修・流用対象）
  - `frontend/src/routes/[org]/[project]/quizzes/+page.svelte:18-26` — クイズ dev プレビューリンク（rank 2a）
  - `frontend/src/lib/components/quiz/coming-soon-placeholder.svelte:5` — 汎用 placeholder（`action` Snippet 対応）
  - `frontend/src/lib/components/galaxy/coming-soon-placeholder.svelte:26-32` — Galaxy dev リンク + 主 Button（rank 2a）
  - `frontend/src/routes/[org]/[project]/galaxy/+page.svelte:16-17` — Galaxy placeholder 呼び出し箇所
  - `frontend/src/routes/[org]/[project]/+page.svelte:14-17` — Overview の `repo.connected ? overviewMock : null`（rank 6 差込先・rank 7 中核）
  - `frontend/src/lib/components/overview/overview-dashboard.svelte` — Sample バッジ追加先（rank 7）
  - `frontend/src/lib/components/overview/coming-soon-placeholder.svelte:12-17` — ぼかしプレビュー構図（rank 7 流用元）
  - `frontend/src/lib/stores/repo-store.svelte.ts:4` — `connected`（常時 truthy 化）/ scan フラグ追加先（rank 7）
  - `frontend/src/lib/stores/project-store.svelte.ts:22-31,51-57` — localStorage 永続パターン（rank 6 流用元）
  - `frontend/messages/ja.json` / `en.json` — Paraglide 文言（ja 主・en 従、288 キー運用。`*_coming_preview` は 244/236 行）
- 規約
  - `CLAUDE.md` — Svelte 5 runes のみ / shadcn-svelte@latest（`ui/` は読み取り専用）/ Tailwind v4 /
    Paraglide 2.0（ja 主・en 従）/ フロントは kebab-case / 警告を無視しない
