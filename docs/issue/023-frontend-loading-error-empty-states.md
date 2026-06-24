# ローディング/エラー/空状態を整備する

## 概要

フロントエンド全域で、素のスピナー・テキスト「読み込み中…」「…」を**レイアウト準拠スケルトン**へ、
握りつぶしている認証/接続エラーを**分類済みリカバリ導線付きエラー**へ、保存/リトライ等の**成功フィードバック**を
付与する横断的な UX 整備 issue である。バックエンド変更は不要で、すべてフロントの表示層（`frontend/src/`）の改修に閉じる。
対象は認証コールバック・ルート/エラーページ・クイズ集中モード・エージェントパイプライン・Overview/Matrix/Repos/
connect-repo/project-switcher の各画面。

## 背景・目的

### 横断テーマ（状態）

DevDebtOps は「コードと知識の二軸技術負債を可視化する」プロダクトであり、デモ/UX の質は
**待ち時間と失敗時にどう見えるか**で大きく左右される。現状は以下の 3 つの綻びが各画面に散在している：

1. **素のスピナー/テキスト待ち。** 多くの画面が `m.common_loading()` や「読み込み中...」「…」の
   素テキスト中央寄せで待ちを表現しており、最終レイアウトと無関係なため体感の遅さと CLS（レイアウトシフト）を生む。
   リポジトリにスケルトンコンポーネントは 1 つも存在しない（`find -iname '*skeleton*'` で 0 件）。
2. **握りつぶしたエラー。** 認証コールバックは OAuth 拒否・cookie 未設定・`users/me` 401・組織なし・`listOrgs` 失敗を
   **すべて同一の汎用日本語文**に潰し、`console.error` も無い。connect-repo / project-switcher も
   network/auth/server の区別やリトライ導線を持たない。失敗フェッチと「確定空」が見分けられない箇所がある。
3. **成功の無反応。** 下書き保存・リトライ等が完了しても視覚フィードバックが弱く、操作が通ったか不安になる。
   一方で `kc-meter.svelte` には 1200ms Tween + `+Xpt` の報酬モーションという良い前例が既にあり、横展開の余地がある。

### 目的

1. 待ちを**レイアウト準拠スケルトン**にし、体感速度と視覚的連続性を上げる（既存の `rounded-lg border bg-card` を流用）。
2. 認証/接続エラーを**分類**し、各分類に**復旧アクション**（再試行・インストール・管理者に依頼・ログインへ戻る等）を添える。
   併せて握りつぶした例外を `console.error` で観測可能にする。
3. 保存/リトライ/報酬に**一貫した成功フィードバック**（toast / パルス / インライン遷移）を付与する。

### 既存資産（流用元）

- **スケルトンの器:** `rounded-lg border bg-card` 等のカードクラス（`overview-dashboard.svelte:51,57,58`）。
- **報酬モーション:** `kc-meter.svelte`（`Tween` 1200ms + `+Xpt`）— 成功フィードバックの横展開元。
- **toast:** `svelte-sonner`（`matrix/debt-actions.svelte:3` が import 実績、`ui/sonner` 配備済み）。
- **Twin ロゴ SVG:** `logo.svelte`（`viewBox="-10 -10 110.6 71.5"` の二体ロゴ）— エラーページの挿絵に流用可能。
- **i18n:** Paraglide 2.0（`messages/ja.json` を主・`en.json` を従）。`error_page_title` / `error_page_go_home` は両方に既存。

> バックエンド不要。本 issue は表示層のみで完結する（API シグネチャ・スキーマ変更なし）。

## タスク

### rank 17 — 認証コールバックのエラー分類（重大）

対象: `frontend/src/routes/login/callback/+page.svelte`。現状 4 分岐がすべて独立して存在するものの、
文言が汎用かつ未ログで、GitHub の `error` / `error_description` クエリは一切読んでいない。

- [ ] OAuth 拒否を新分岐として追加する。`page.url.searchParams` の `error` / `error_description`
      （例 `access_denied`）を読み、「GitHub での認可が拒否されました」系の文言を出す（現状 `code`/`state` のみ読取）。
- [ ] cookie 未設定 / `!res.ok`（現 L21-24）を「セッションを確立できませんでした」に分離する。
- [ ] `users/me` 相当 401（`!auth.isAuthenticated`、現 L31-34）を「セッション未確立」系に分離する。
- [ ] `listOrgs` 失敗（現 `catch` L44-45。`err` を握りつぶしている）と組織なし（現 L42）を分離し、
      組織なしは「組織が見つかりませんでした」、`listOrgs` 失敗は「ダッシュボードへの遷移に失敗しました（再試行）」とする。
- [ ] 各分類に**復旧アクション**を添える（OAuth 拒否/セッション失敗→「ログイン画面に戻る」、
      `listOrgs` 失敗→「再試行」ボタンで `onMount` 相当を再実行）。現状の復旧導線は L58-60 の「ログイン画面に戻る」リンクのみ。
- [ ] 握りつぶしている分岐（特に `catch` L44）で `console.error` を出し、観測可能にする（現状 `console.error` は 0 件）。
- [ ] エラー表示を素の `text-destructive`（現 L57）から、`+error.svelte` 等と一貫したブランドスタイルへ寄せる（Logo の流用可）。
- [ ] 文言キーを `messages/ja.json` / `en.json` に追加（`auth_error_oauth_denied` / `auth_error_session` /
      `auth_error_no_org` / `auth_error_dashboard` / `common_retry` 等、ja 主・en 従）。

### rank 18 — ルートページの入口 / エラーページの出口（中）

- [ ] **ルートページ** `frontend/src/routes/+page.svelte`（現状 h1 + p のみ、クリック可能要素ゼロ）に
      「GitHub でサインイン / はじめる」CTA を追加し、`resolve("/login")` へ遷移させる。
- [ ] ルートページで認証済みなら既定 org へ自動リダイレクトする（`auth.isAuthenticated` 判定。
      callback の `listOrgs → defaultOrg` 解決ロジックを共通化して流用可）。
- [ ] **エラーページ** `frontend/src/routes/+error.svelte` に Twin SVG（`logo.svelte` 流用）を追加する
      （現状は `page.status` 見出し + `m.error_page_title()` + `m.error_page_go_home()` のテキストのみで挿絵なし）。
- [ ] エラーページの戻り先に「プロジェクト一覧へ戻る（`/[org]`）」導線を追加する
      （現状の戻り先は `resolve("/")` のルートのみ。org コンテキストがある場合は `/[org]` を優先）。

> 注: `+error.svelte` は既にブランド適用済みで素ページ回避は達成済み。本 issue では Twin SVG と一覧導線の**追加のみ**。

### rank 26 — 成功 / 永続化フィードバック（中）

- [ ] **下書き保存:** `frontend/src/lib/components/quiz/focus-mode.svelte`（保存ステータスは現 L36-40 で
      `◌ saving` / `● saved` のテキストトグルのみ）に、保存確定時のチェックのパルス演出または toast を付与する。
      `quiz-store.svelte.ts` の `saveDraft`（L27-33、同期的に `saving`→`saved`）の遷移にフックする。
- [ ] **エージェントリトライ:** `frontend/src/lib/components/agents/pipeline-node.svelte`（現 L15-19、`retryable` 時に
      `agents.retry` を呼ぶだけ）で、`AgentStatusIcon`（import 済み）の回転状態 + toast を配線し、
      「リトライ中…」→結果のインライン遷移を見せる。`agent-store.svelte.ts` の `retry`（L31-37、`status="analyzing"` に
      変えるのみ）にトースト/遷移を足す。
- [ ] toast は `svelte-sonner` を使い、`focus-mode` / `pipeline-node` の双方で import する（両者とも現状未 import）。
- [ ] **KC 報酬パターンの横展開:** `kc-meter.svelte`（Tween 1200ms + `+Xpt`）の報酬モーションを、上記の保存/リトライ
      成功演出のトーン基準として再利用する（同一の `success` トークン・タイミングに揃える）。

> 注: `agent-store` / `quiz-store` は現状モック配線（実 API は後続 issue）。本 issue は**フィードバック層の付与のみ**で、
> 採点/実エージェント連携には踏み込まない。

### rank 27 — 不定スピナー / テキスト待ちをレイアウト準拠スケルトンへ（中）

スケルトンコンポーネントはリポジトリに存在しない（0 件）。共通の `skeleton`（shadcn-svelte）または
`ui/` 外の自作スケルトン部品を 1 つ用意し、各画面へ展開する。既存の `rounded-lg border bg-card` を器に使う。

- [ ] **共通スケルトン部品**を追加する（`bunx shadcn-svelte@latest add skeleton`、または
      `frontend/src/lib/components/ui-ext/skeleton.svelte` 相当の自作。`ui/` 直下は読み取り専用のため `ui/` 外に置く）。
- [ ] **Matrix:** `frontend/src/routes/[org]/[project]/matrix/+page.svelte`（現 L78-79 が `loading` 時に
      `m.common_loading()` の素テキスト中央寄せ）を、`DebtListRow`（L88-93 の `ul`）の形を模した 5-8 行の
      ゴースト行に置き換える。
- [ ] **Repos ブランチ切替:** `frontend/src/routes/[org]/[project]/repos/+page.svelte`（現 L95-96 が `treeLoading` 時に
      「読み込み中...」でツリーを空に）を、ゴーストツリー（インデント付き行のスケルトン）に置き換える。
- [ ] **org ページ:** `frontend/src/routes/[org]/+page.svelte`（現 L46-47 が `project.loading && projects.length===0` 時に
      単独 `…`）を、プロジェクトカードのゴーストグリッドに置き換える。
- [ ] **Overview 統計カード:** `frontend/src/lib/components/overview/overview-dashboard.svelte` の stat-card 群（L32-48）の
      ゴースト矩形を用意する。**現状 Overview は `overviewMock` 由来で同期描画**（`[org]/[project]/+page.svelte:17`）のため、
      後続で `getOverview()` を await する際に差し込めるよう**スケルトン分岐の器だけ用意**する（実 await 配線は本 issue 範囲外）。
- [ ] **project-switcher にタイムアウト→リトライ:** rank 29 と統合（下記参照）。

### rank 28 — connect-repo（repo-picker）の堅牢化（中）

対象: `frontend/src/lib/components/repo/repo-picker.svelte`。`PickerState`（L11）に
`loading`/`ready`/`error`/`not_installed` は定義済みで分岐の足場はある。

- [ ] **loading 分岐**（現 L59-60、「リポジトリを読み込み中...」の素テキスト）を、リスト形のスケルトン
      （5-8 ゴースト行、`ul`/`li` 構造に合わせる）に置き換える（rank 27 の共通部品を流用）。
- [ ] **not_installed 分岐**（現 L66-79）が `{#if appSlug}`（L69）でラップされ、`appSlug` 空時に
      インストール/ヘルプ affordance が完全消失する問題を直す。`appSlug` 不在時のフォールバックとして
      汎用 GitHub Apps URL（`https://github.com/apps`）または「管理者に依頼してください」ガイダンスを**常に**出す。
- [ ] **error 分岐**（現 L61-65、`errorMessage` = `err.message` そのまま表示 L42）を、
      network / auth / server のカテゴリに分類して文言と復旧導線を出し分ける
      （network→再試行、auth→ログインへ、server→時間を置いて再試行）。`AppNotInstalledError`（import 済み L2）の
      分岐は維持しつつ、それ以外の `Error` をカテゴリ判定する。

### rank 29 — プロジェクトスイッチャーの状態分岐（中）

対象ストア: `frontend/src/lib/stores/project-store.svelte.ts`。`loading`（L17 で `$state(false)`）は存在し
`loadList`（L38-48）で追跡するが、**error は未追跡**（`catch` で `list=[]` にするのみ、L42-43）。
対象 UI: `frontend/src/lib/components/shell/project-switcher.svelte`（Popover 本体 L104-125）。

- [ ] `project-store` に `error` state（`$state<string | null>(null)` 等）を追加し、`loadList` の `catch`（L42-43）で
      `error` をセットする（現状は空リスト化のみで失敗が「確定空」と区別不能）。
- [ ] `project-switcher.svelte` の Popover 本体（L104-125、現状 recent/all/空のみ描画）に状態分岐を入れる：
  - **読込中**（`project.loading`）= リスト形スケルトン（rank 27 の共通部品）
  - **失敗**（`error != null`）= エラー行 + 「再試行」ボタン（Popover を開くと `$effect` L25-29 で `loadList` を再実行する設計を利用）
  - **空**（`!loading && !error && list.length===0`）= 確定空メッセージのみ（現 L119 の `project_switcher_empty()` をこの分岐に限定）
- [ ] **タイムアウト→リトライ:**（rank 27 の同項目）`loadList` に一定時間で打ち切る扱いを加え、
      タイムアウト時は上記「失敗」分岐に合流させ「再試行」を出す。
- [ ] 追加文言キーを `messages/ja.json` / `en.json` に追加（`project_switcher_error` / `common_retry` 等）。

### 共通（i18n / スタイル規律）

- [ ] 追加文言はすべて `messages/ja.json`（主）/ `en.json`（従）に対で追加し、Paraglide の `m.*()` 経由で参照する。
- [ ] スケルトン/エラー/フィードバックの新規部品は `frontend/src/lib/components/ui/` の**外**に置き、
      `$lib/utils.ts` の `cn` でクラス合成する（`ui/` 直下は読み取り専用）。kebab-case ファイル名・Svelte 5 runes を厳守。

## 完了条件

- 認証コールバックで OAuth 拒否 / セッション未確立 / 組織なし / `listOrgs` 失敗が**それぞれ異なる文言と復旧導線**で
  表示され、握りつぶしていた失敗が `console.error` に出ること（`login/callback/+page.svelte`）。
- ルートページに動作する「サインイン / はじめる」CTA があり、認証済みなら既定 org へリダイレクトすること。
- `+error.svelte` に Twin SVG（`logo.svelte` 由来）と「一覧へ戻る（`/[org]` 優先）」導線があること。
- 下書き保存・エージェントリトライの成功時に視覚フィードバック（パルス or toast、リトライは「リトライ中…」→結果の
  インライン遷移）が出ること。
- Matrix / Repos ツリー / org ページ / repo-picker の待ち表示が、素テキストではなく**レイアウト準拠スケルトン**に
  なっていること（CLS が抑えられ、最終レイアウトと形が一致する）。
- repo-picker の `not_installed` で `appSlug` 不在でもインストール/ヘルプ導線が消えないこと、error がカテゴリ別に出ること。
- project-switcher が **読込中 / 失敗（再試行付き）/ 確定空** を見分けて表示し、失敗と空が混同されないこと。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` がパスすること。

## 対象外・保留

- **新規パイプライン issue の中身に踏み込まない（保留）:** rank 26 で触れる `agent-store` / `quiz-store` は現状モック配線で、
  実エージェント連携・採点本体は後続 issue（コード内 TODO 済み）。本 issue は**フィードバック層の付与のみ**に限定し、
  実 API 連携は範囲外とする。
- **Overview の実データ await（範囲外）:** Overview は現在 `overviewMock` 由来で同期描画（`[org]/[project]/+page.svelte:17`）。
  rank 27 の Overview スケルトンは**器（スケルトン分岐）の用意まで**とし、`getOverview()` を await する非同期化は
  Overview 集計バックエンドの後続 issue（仕様書 §10.3）で行う。
- **バックエンド変更（不要）:** 本 issue は表示層のみ。API シグネチャ・Zod スキーマ・DB は変更しない。

> droppedRanks: なし（束ねられた 6 件の指摘はすべて valid=true・alreadyImplemented=false として検証済み、全件タスク化）。

## 参考

### 元レビュー rank 対応

- **rank 17**（重大/S/認証）→「rank 17 — 認証コールバックのエラー分類」
- **rank 18**（中/S/アプリシェル）→「rank 18 — ルートページの入口 / エラーページの出口」
- **rank 26**（中/M/Quizzes,Agents）→「rank 26 — 成功 / 永続化フィードバック」
- **rank 27**（中/M/AppShell,Overview,Repos,Matrix,Connect）→「rank 27 — レイアウト準拠スケルトン」
- **rank 28**（中/M/ConnectRepo）→「rank 28 — connect-repo（repo-picker）の堅牢化」
- **rank 29**（中/S/ProjectSwitcher）→「rank 29 — プロジェクトスイッチャーの状態分岐」

### 関連 file（検証済みの実在パス）

- `frontend/src/routes/login/callback/+page.svelte` — 認証コールバック（L11-47 が分岐本体、`console.error` 0 件）
- `frontend/src/routes/+page.svelte` — ルートページ（h1 + p のみ、CTA なし）
- `frontend/src/routes/+error.svelte` — エラーページ（ブランド済み、Twin SVG / 一覧導線が未着手）
- `frontend/src/lib/components/quiz/focus-mode.svelte` — 保存ステータス（L36-40）
- `frontend/src/lib/stores/quiz-store.svelte.ts` — `saveDraft`（L27-33）
- `frontend/src/lib/components/agents/pipeline-node.svelte` — リトライ（L15-19）
- `frontend/src/lib/stores/agent-store.svelte.ts` — `retry`（L31-37）
- `frontend/src/lib/components/quiz/kc-meter.svelte` — 報酬モーション（Tween 1200ms + `+Xpt`、横展開元）
- `frontend/src/routes/[org]/[project]/matrix/+page.svelte` — loading 素テキスト（L78-79）/ DebtListRow ul（L88-93）
- `frontend/src/routes/[org]/[project]/repos/+page.svelte` — treeLoading（L95-96）
- `frontend/src/routes/[org]/+page.svelte` — 単独「…」（L46-47）
- `frontend/src/lib/components/overview/overview-dashboard.svelte` — stat-card 群（L32-48）/ カードクラス（L51,57,58）
- `frontend/src/routes/[org]/[project]/+page.svelte` — Overview は overviewMock 由来の同期描画（L17）
- `frontend/src/lib/components/repo/repo-picker.svelte` — loading/error/not_installed 分岐（L59-79）、errorMessage（L42）
- `frontend/src/lib/stores/project-store.svelte.ts` — `loadList`（L38-48、error 未追跡）
- `frontend/src/lib/components/shell/project-switcher.svelte` — Popover 本体（L104-125）、loadList 再実行 `$effect`（L25-29）
- `frontend/src/lib/components/logo.svelte` — Twin ロゴ SVG（`viewBox="-10 -10 110.6 71.5"`）
- `frontend/src/lib/components/matrix/debt-actions.svelte` — `svelte-sonner` import 実績（L3）
- `frontend/src/lib/components/ui/sonner/` — toast 配備済み
- `frontend/messages/ja.json` / `en.json` — `error_page_title` / `error_page_go_home`（L16-17、両方に既存）

### 規約

- `CLAUDE.md` — フロント kebab-case / Svelte 5 runes のみ / shadcn-svelte@latest（`ui/` は読み取り専用）/
  Tailwind v4 / Paraglide 2.0（ja 主・en 従）/ 警告をエラーとして扱う / `bun run check`・`lint`・`test:unit` ゲート
