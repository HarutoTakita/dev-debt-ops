# IA/ナビ整備とデモの誠実さ（Soon バッジ・pill・⌘K・パンくず）

## 概要

サイドバー・Topbar・パンくずの IA/ナビ周りに残る「嘘」を是正する。具体的には
(1) 未実装機能（galaxy/quizzes/agents/learning/settings）への `comingSoon` フラグ未設定で
**Soon バッジが一切点灯していない**問題、(2) Topbar の ⌘K が `toast.info("coming soon")` を
出すだけの**死んだコマンドパレット**、(3) Matrix の pill がデータ無視の**固定値 `"8"`**、
(4) パンくず末端が常に非リンクで**詳細ルート（debtId/sessionId）を表現できない**問題を直す。
横断テーマは「何が本物かに誠実であれ + IA/ナビゲーション」。**バックエンド不要**（全てフロント内の
データ配線・表示是正）。

## 背景・目的

このアプリは観測対象リポジトリ単位で「理解する → 返済する」を案内するナビ構造を持つが、
現状デモを通すと**ナビが実態と食い違う**箇所が複数ある。プレースホルダ機能があたかも
動くかのように見え（Soon バッジ未点灯）、固定値の pill がデータ駆動を装い（Matrix `"8"`）、
Topbar の検索枠は ⌘K を押しても何も起きない（死んだバインディング）。これらは
「何が本物かに誠実であれ」というプロダクト原則に反し、デモの信頼性を損なう。

本 issue は IA/ナビ整備の一環として、**実装済みの表示機構を正しいデータに配線し直す**ことを
主眼とする。多くは既にレンダリング側（バッジ・aria-current・pill 分岐）が用意済みで、
欠けているのは設定値・フラグ・配線だけである。フルのコマンドパレット本体や共有パンくず
ストアの新設のような greenfield 部分は、最小の誠実化（無効表示・末端のリンク化）に絞り、
過大な新規実装は「対象外・保留」へ回す。

## タスク

### Soon バッジ点灯と未実装項目の pill 抑制（rank 1）

`frontend/src/lib/config/nav.ts` の `comingSoon?: boolean`（nav.ts:30）は型宣言だけ存在し、
**どの項目にも `true` が設定されていない**。一方 `nav-item.svelte` は折りたたみ時
（nav-item.svelte:53-54 `{:else if item.comingSoon}` → `m.shell_soon()`）と展開時
（nav-item.svelte:71-72 `<Badge>{m.shell_soon()}</Badge>`）の両方で **Soon バッジを描画する
分岐を既に持ち**、`aria-current={active ? "page" : undefined}`（nav-item.svelte:42, 62）も
既に付与済み。`shell_soon` メッセージキーも ja.json/en.json に存在（ja.json:82）。
つまり**バッジ描画・aria-current は完成済みで、欠けているのは nav.ts のフラグだけ**。

- [ ] `nav.ts` の未実装 5 項目に `comingSoon: true` を設定する：
      galaxy（nav.ts:60-67）/ quizzes（nav.ts:75-82）/ agents（nav.ts:83）/
      learning（nav.ts:84-89）/ settings（nav.ts:108-113）
- [ ] **pill が Soon バッジを覆い隠す問題を解消する。** `nav-item.svelte` の分岐は
      `{#if pillText}…{:else if item.comingSoon}`（nav-item.svelte:51-55, 67-73）で、
      pill が `comingSoon` より優先される。galaxy（`pill: () => galaxy.myKc…` nav.ts:66）と
      quizzes（`pill: () => quiz.availableCount…` nav.ts:81）は pill を返すため、
      `comingSoon: true` を立てるだけでは **pill が出続け Soon が出ない**。
      pill 分岐に `!item.comingSoon &&` を足す（`{#if pillText && !item.comingSoon}`）か、
      coming-soon 項目の `pill` クロージャを外して、未実装項目では**数値 pill を抑制し
      Soon バッジを表示**する。agents/learning/settings は pill 無しのため対応不要。
- [ ] aria-current は既に実装済み（nav-item.svelte:42, 62）。**追加作業なし**（確認のみ）。

### Matrix pill をデータ駆動に（rank 14）

`nav.ts:73` の matrix 項目は `pill: () => "8"` の**ハードコード文字列**。同セクションの
galaxy（nav.ts:66）と quizzes（nav.ts:81 `quiz.availableCount > 0 ? String(...) : null`）は
ストア値から導出する**データ駆動**になっており、matrix だけが固定値で浮いている
（現状の `MOCK_DEBTS` がたまたま 8 件なので一見正しく見えるが、データ変更に追随しない）。

- [ ] matrix の pill を `MOCK_DEBTS`（`frontend/src/lib/api/mock/debts.ts:5` で
      `export const MOCK_DEBTS: DebtItem[]`、現在 8 件）から導出する。最小修正は
      `import { MOCK_DEBTS }` の上で `pill: () => (MOCK_DEBTS.length > 0 ? String(MOCK_DEBTS.length) : null)`。
      quizzes の `availableCount > 0 ? … : null` パターン（nav.ts:81）に揃え、
      **0 件のときは pill 非表示**にする。
- [ ] （任意・後述「対象外・保留」も参照）将来的に open 件数のみを数えたい場合は
      `status === "open"` でフィルタした件数にする。`DebtItem.status` は mock に存在する
      （debts.ts の各エントリに `status: "open"` 等）。

> 注: レビュー rank 14 が言及する `matrix.openCount` ストア配線は greenfield（matrix-store 不在）。
> 本タスクでは `MOCK_DEBTS.length` 直結の最小修正のみを行い、ストア新設は「対象外・保留」へ回す。

### ⌘K の誠実化（死んだバインディングの是正）（rank 12）

`frontend/src/lib/components/shell/command-palette-trigger.svelte` は、`open()` が
`toast.info(m.shell_coming_soon(...))` を出すだけ（command-palette-trigger.svelte:7-9）で、
⌘K/Ctrl+K の keydown（同 11-16）も同じ `open()` を呼ぶ。にもかかわらずボタンには
`⌘K` の kbd ヒント（同 28-30）が出ており、**「⌘K が効く」という誤った見た目**になっている。
このトリガは `topbar.svelte:45` で実際に描画されている（import は topbar.svelte:11）。

- [ ] **最小の誠実化（本 issue のスコープ）:** `⌘K` の kbd ヒント（command-palette-trigger.svelte:28-30）を
      削除するか、`coming soon` であることが明確に伝わる無効表示にする。
      「押せそうなのに toast しか出ない」状態を解消し、見た目とふるまいを一致させる。
- [ ] keydown ハンドラ（command-palette-trigger.svelte:11-16）が `⌘K` を奪って
      `toast` を出す挙動は、ヒント削除に合わせて整理する（ヒントを消すなら keydown も外し、
      ブラウザ/他機能のショートカットを横取りしない）。

> フル機能（`allNavItems`（nav.ts:119）の曖昧検索 + `project.recentProjects(orgSlug)`/`project.list`
> によるプロジェクト横断ジャンプ）の**パレット本体新設は greenfield のため「対象外・保留」**へ回す。
> 配線先のデータソースは全て存在する（`allNavItems` nav.ts:119、`project.recentProjects`
> project-store.svelte.ts:60、`project.list` project-store.svelte.ts:17）が、横断ジャンプを
> 成立させるには先に `project.loadList(orgSlug)` を呼ぶ必要がある点を後続 issue に申し送る。

### パンくず末端のリンク化と詳細ルート検出（rank 25）

`frontend/src/lib/components/shell/breadcrumbs.svelte` の末端は非クリックの
`<span class="truncate text-muted-foreground">{current.label()}</span>`（breadcrumbs.svelte:31）。
`current` は top-level の nav 項目からのみ算出され（breadcrumbs.svelte:14-18、overview 除外）、
`page.params.debtId`/`sessionId` の検出も 4 セグメント目も無い。詳細ルートは実在する：
`src/routes/[org]/[project]/matrix/[debtId]/`、`src/routes/[org]/[project]/quizzes/[sessionId]/`
（いずれも `+page.svelte` + `+page.ts` を持つ）。

- [ ] アクティブな機能パンくず（現状 `<span>` の `current.label()`、breadcrumbs.svelte:29-32）を
      `resolve(current.route(ctx))` への**リンク**にする。`current.route(ctx)` は既に同ファイルで
      使用済み（breadcrumbs.svelte:16 の `isActiveRoute(i.route(ctx), …)`）のため流用するだけ。
      最末端（詳細クラムがある場合）はリンクにせず現在地として残す。
- [ ] **詳細セグメント（4 つ目）の検出を追加する。** `page.params.debtId` / `page.params.sessionId`
      を検出し（両ルートフォルダの存在で params 名は確定済み）、存在時に末端へ
      「詳細」クラム（debtId/sessionId 由来のラベル）を push する。最小実装は
      breadcrumbs.svelte 内で params を見て 1 段足すだけでよい。

> 共有パンくずストア（GitLab スタイルのシングルトン push）は未実装で greenfield。
> 4 セグメント目の表現は breadcrumbs.svelte 内の params 検出で成立するため、
> **共有ストア新設は「対象外・保留」**へ回す。

### Org ランディングに「Recent」行（rank 32）

`frontend/src/routes/[org]/+page.svelte` は `project.list`（+page.svelte:19）から
フラットなグリッド（同 63-83）を描画するだけで、Recent もピン留め行も無い。
`project.recentProjects(orgSlug)`（project-store.svelte.ts:60）は実装済みだが現状
`project-switcher.svelte` でしか使われていない。org ページは既に `$effect` 内で
`project.loadList(orgSlug)`（+page.svelte:15-17）を呼び、`recentProjects` はその `list` に
対して解決するため、**Recent 行はグリッド上に `project.recentProjects(orgSlug)` を並べるだけ**で
成立する（低コスト）。

- [ ] `[org]/+page.svelte` のグリッド（+page.svelte:63-83）の上に「Recent」行を追加し、
      `project.recentProjects(orgSlug)`（project-store.svelte.ts:60）の結果を新しい順に並べる。
      空（未訪問）なら行ごと非表示。
- [ ] **`recentProjects` が populate される前提を確認する。** 直近性は
      `project.touch(orgSlug, projectId)`（project-store.svelte.ts:51）の呼び出しに依存するが、
      これがプロジェクト訪問時に呼ばれているか未確認。`[org]/[project]/+layout`（または
      `+layout.ts`）で訪問時に `project.touch(...)` を呼ぶ配線が無ければ追加する
      （無いと Recent 行が常に空になる）。

> 「ピン留めプロジェクト」拡張は greenfield のため「対象外・保留」へ回す。現状の
> ピン留めモデル（`sidebar-store.svelte.ts` の `pinnedIds`/`togglePin`/`isPinned`）は
> **nav 項目 id でキーされ**ており、プロジェクト単位のピン留めには新ストアか
> project-store の拡張が要る。

## 完了条件

- サイドバーで galaxy/quizzes/agents/learning/settings に **Soon バッジが表示**され、
  galaxy/quizzes では数値 pill ではなく Soon バッジが出る（pill が Soon を覆わない）。
  折りたたみ時のツールチップにも Soon が出る。
- Matrix の pill が `MOCK_DEBTS` の件数から導出され（現状 8）、mock を増減すると pill も追随する。
  0 件時は pill が消える。
- Topbar の検索枠から ⌘K の誤ったヒント表示が消え、**見た目とふるまいが一致**する
  （押せそうなのに toast だけ、という状態が無い）。
- パンくずのアクティブ機能クラムが**リンク**になり、`/matrix/[debtId]` または
  `/quizzes/[sessionId]` を開くと末端に「詳細」クラムが 4 つ目として表示される。
- Org ランディングに「Recent」行が出て、最近開いたプロジェクトが新しい順に並ぶ
  （未訪問時は非表示）。プロジェクト訪問で `touch` が呼ばれ Recent が populate される。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` が通る。
- バックエンド変更は無い（**バックエンド不要**）。

## 対象外・保留

検証で valid=true だが本 issue では**最小の誠実化に絞り**、以下の greenfield 拡張は
後続 issue へ申し送る（いずれも「無効/最小表示」までを本 issue で担保する）：

- **⌘K コマンドパレット本体（rank 12 のフル実装）.** `allNavItems`（nav.ts:119）の曖昧検索 +
  `project.recentProjects`/`project.list` を配線したパレット UI は新規コンポーネントが必要。
  本 issue は「死んだ ⌘K の誠実化（ヒント削除/無効表示）」までに留める。
  申し送り: 横断ジャンプには先に `project.loadList(orgSlug)` が必要。
- **Matrix `openCount` ストア（rank 14 の理想形）.** matrix-store は不在で、matrix ページは
  `listDebts()` をローカル `$state` に読むだけ。共有ストアへ `openCount` を公開するのは
  greenfield。本 issue は `MOCK_DEBTS.length` 直結の最小データ駆動化までとする。
- **共有パンくずストア（rank 25 の GitLab スタイル）.** シングルトンへ各ページが push する
  方式は未実装。本 issue は breadcrumbs.svelte 内の `page.params` 検出で 4 セグメント目を
  表現する最小実装までとする。
- **ピン留めプロジェクト（rank 32 の拡張）.** 現状のピン留め（`sidebar-store.svelte.ts` の
  `pinnedIds`/`togglePin`/`isPinned`）は nav 項目 id 単位で、プロジェクト単位ピンには
  新ストア/拡張が要る。本 issue は「Recent」行までとする。

（valid=false で完全に除外した指摘は無し。alreadyImplemented=true の事実は
rank 1 の「aria-current は実装済み（追加作業なし）」のみで、当該作業はタスクから除外済み。）

## 参考

### 元レビュー rank 対応

| rank | 要点 | 本 issue での扱い |
|---|---|---|
| rank 1 | Soon バッジ点灯 + 未実装項目の pill 抑制 | タスク化（nav.ts フラグ + nav-item.svelte の pill 分岐） |
| rank 12 | ⌘K コマンドパレット配線 | **最小の誠実化のみ**タスク化（本体は対象外・保留） |
| rank 14 | Matrix pill をデータ駆動 | タスク化（`MOCK_DEBTS.length` 直結。ストア化は対象外・保留） |
| rank 25 | パンくず末端のリンク化 + 詳細ルート | タスク化（リンク化 + params 検出。共有ストアは対象外・保留） |
| rank 32 | Org ランディングに Recent/ピン留め | Recent 行をタスク化（ピン留め拡張は対象外・保留） |

### 関連 file（実在確認済み）

- `frontend/src/lib/config/nav.ts` — `comingSoon`（30）/ matrix pill `"8"`（73）/
  galaxy・quizzes pill（66, 81）/ `allNavItems`（119）/ `isActiveRoute`（125）
- `frontend/src/lib/components/shell/nav-item.svelte` — Soon バッジ分岐（53-54, 71-72）/
  aria-current（42, 62）/ pill 分岐（51, 67）
- `frontend/src/lib/components/shell/command-palette-trigger.svelte` — `open()`（7-9）/
  keydown（11-16）/ ⌘K ヒント（28-30）。`topbar.svelte:45` で描画
- `frontend/src/lib/components/shell/breadcrumbs.svelte` — `current` 算出（14-18）/
  末端 `<span>`（29-32）
- `frontend/src/lib/api/mock/debts.ts` — `MOCK_DEBTS`（5、現在 8 件）
- `frontend/src/lib/stores/project-store.svelte.ts` — `list`（17）/ `touch`（51）/
  `recentProjects`（60）
- `frontend/src/routes/[org]/+page.svelte` — プロジェクトグリッド（19, 63-83）/
  `loadList` $effect（15-17）
- 詳細ルート: `frontend/src/routes/[org]/[project]/matrix/[debtId]/`、
  `frontend/src/routes/[org]/[project]/quizzes/[sessionId]/`
- i18n: `frontend/messages/ja.json`（`shell_soon`:82 / `shell_command_palette`:87 /
  `shell_coming_soon`:89）・`en.json`

### 規約（CLAUDE.md）

- Svelte 5 runes のみ（`$:`/`writable()` 不使用）、shadcn-svelte@latest（`ui/` は読み取り専用）、
  Tailwind v4、Paraglide 2.0（ja 主・en 従）、kebab-case ファイル命名。
- 「何が本物かに誠実であれ」— プレースホルダ/死んだバインディング/固定値を**そう見えないように
  装わない**。`bun run check` / `bun run lint` / `bun run test:unit` を通す。
