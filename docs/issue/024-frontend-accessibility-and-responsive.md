# アクセシビリティとレスポンシブを底上げする

## 概要

Galaxy / Overview / Matrix / Quiz と App Shell に散在する UX レビュー指摘のうち、
**アクセシビリティ（a11y）とレスポンシブ**に関わるものを 1 本に束ねて底上げする chore。
具体的には (1) 色のみに依存した符号化の解消、(2) 可視化ノードの focus-visible とキーボード操作、
(3) `prefers-reduced-motion` の尊重、(4) 散布図ドット / 星ノードの可読化、
(5) Galaxy のモバイルレスポンシブ化、(6) テーマトグル公開 + 無効ナビ項目のキーボード発見性、を扱う。
**バックエンド変更は不要**（すべてフロント `frontend/src/` 内で完結）。

## 背景・目的

元レビューの横断テーマは「アクセシビリティ」である。DevDebtOps の一級概念である
Knowledge Coverage（KC）や二軸負債は、Galaxy の星 / Overview の散布図 / Matrix の優先度バッジ
といった**密度の高い可視化**で表現されるが、現状これらは色（cyan / teal / red など）と
発光・不透明度だけで状態を区別しており、色覚特性や低コントラスト環境では情報が失われる。
さらに SVG / 絶対配置ノードはサイズが固定（8〜12px）で、フォーカスリングもなく、
モーション設定を無視した拡大アニメーションを持つ。Galaxy マップはデスクトップ前提のレイアウトで
モバイルでは破綻しやすい。テーマトグルは UI から到達できず、無効ナビ項目はフォーカス不能な
40% 不透明 div で「存在するのに発見できない」状態にある。

これらは個別には小粒だが、**デモ / 採用評価の第一印象に直結する基礎品質**であり、
横断テーマとして一括で底上げする価値が高い。各指摘は前段の実コード監査で
`valid=true` を確認済みのものだけをタスク化する（`alreadyImplemented=true` / `valid=false` は
「対象外・保留」へ理由付きで退避）。

> 注: file:line は監査 evidence で実在を確認した現行行に揃える。レビュー初稿が引いていた
> 一部の行番号・前提（例: 「星に onclick が無い」）は現行コードと食い違っており、本書では
> 現行の実コードを正とする。

## タスク

### rank 10 — 色のみ符号化の解消（重大 / M / Galaxy・Overview・Matrix）

dot / 星 / バッジに**色以外の手がかり**（グリフ・パターン・リング・`aria-label`）を足す。
リスト・ツールチップには既にテキストラベルが併記されているため、色のみ符号化が
実害になるのは主に SVG / 視覚ノードである。

- [ ] `frontend/src/lib/components/galaxy/star-node.svelte:11-18` — `star` / `dim_star` /
      `black_hole` / `unexplored` が現状は色 + glow + 不透明度のみで区別されている。
      `black_hole` に内側グリフ（例: 中心ドット / リング）を、`dim_star` に塗りパターン
      （`bg-*` 上の網点 / ストライプ）を加え、色覚に依存しない判別手がかりを足す。
- [ ] `frontend/src/lib/components/galaxy/galaxy-labels.ts:14-19` — `masteryDot`（凡例 / リストの
      色ドット）も純色のみ（例: `black_hole: "bg-red-500"`）。star-node と整合する形で
      グリフ / パターン手がかりを付与する（凡例とノードで見た目を一致させる）。
- [ ] `frontend/src/lib/components/overview/debt-matrix.svelte:62` — 危険ドットには既に
      `ring-2 ring-destructive/25` が付いているが、`'!'` 等の**非色マーカーが無い**。
      危険ゾーンのドットに `!` グリフ（または同等の記号オーバーレイ）を追加する。
- [ ] `frontend/src/lib/components/matrix/priority-badge.svelte:26` — 2 本ミニゲージのラッパー
      `<span ... aria-hidden="true">` を、構造化した `aria-label`
      （例: `Priority P0, code debt 70, knowledge gap 80`）を持つ要素へ変更する。
      現状は外側 div（line 22）に `title="コード負債 X / 理解欠落 Y"` があるのみで、
      スクリーンリーダー向けの優先度 + 2 軸値の読み上げが無い。

### rank 11 — 可視化ノードの focus-visible とキーボード操作（重大 / M / Galaxy・Overview）

- [ ] `frontend/src/lib/components/galaxy/star-node.svelte:24-30` — 星は既に
      `<button type="button" aria-label={file.path}>` で `Tooltip.Trigger` 配下にあり
      フォーカス可能（レビュー初稿の「onclick / フォーカス可能ラベルが無い」は**現行では解消済み**）。
      残作業として `class` に `focus-visible:ring-2`（+ `ring-offset`）を追加する。
- [ ] `frontend/src/lib/components/galaxy/star-node.svelte:29` — 現状 `size-3`（12px）で
      ヒットターゲットが小さい。**見た目を変えない不可視パディング**（透明な疑似拡張 /
      `before:` などで実クリック領域を ~24px に）を足し、タップ / フォーカスを取りやすくする。
- [ ] `frontend/src/lib/components/overview/debt-matrix.svelte:58-70` — 散布図ドットは既に
      `<button>` + `onfocus`/`onblur` でフォーカス時にツールチップを開く（focus-shows-tooltip は
      **部分的に達成済み**）。残作業として line 61-62 の class に `focus-visible:ring-2` を追加し、
      `size-2`/`size-2.5`（8〜10px）のドットに不可視の ~24px ヒットターゲットを足す。
- [ ] 星ツールチップがキーボードフォーカスで開くことを**実機 / キーボード操作で検証**する
      （`Tooltip.Trigger` はフォーカスを扱うため恐らく既に動作するが、`{#snippet child}` 経由の
      合成で実際に開くかを確認する）。

### rank 16 — `prefers-reduced-motion` の尊重（中 / S / Quiz・Galaxy・Overview）

現状 `frontend/src` 配下に `prefers-reduced-motion` / `motion-reduce` / `matchMedia` は
**1 件も存在しない**（grep 0 件）。完全に未対応。

- [ ] `frontend/src/routes/layout.css` にグローバルな
      `@media (prefers-reduced-motion: reduce)` ルールを追加し、トランジション / アニメーションを
      抑制する（このファイルが `+layout.svelte` が import するグローバルスタイルシート。
      **本リポジトリに `app.css` は存在しないため、規約名に惑わされず `layout.css` に置く**）。
- [ ] `frontend/src/lib/components/quiz/kc-meter.svelte:11-14` — 無条件の `Tween`
      （duration 1200 / cubicOut）に reduced-motion ガードを足し、`matchMedia` 一致時は補間を
      0（即時反映）にする。**ただし `+Xpt` の最終表示は維持**する（line 22 の `+...pt` 表示を残す）。
- [ ] `frontend/src/lib/components/galaxy/star-node.svelte:29`（`hover:scale-150`）と
      `frontend/src/lib/components/overview/debt-matrix.svelte:61`（`hover:scale-150`）に
      `motion-reduce:hover:scale-100` バリアントを足し、reduced-motion 時はホバー拡大を止める。

### rank 20 — 可視化ノードの可読化（重大 / M / Overview・Galaxy）

3 つのサブ項目（散布図ドットの拡大 + 件数チップ、KC スケールの星、共有 viewBox での共リフロー）が
すべて未実装。引用行はいずれも現行コードで実在を確認済み。

- [ ] `frontend/src/lib/components/overview/debt-matrix.svelte:60-63` — ドットサイズが
      `isDanger()` 真偽のみ（危険 `size-2.5` / 他 `size-2`）で決まっている。サイズを `size-3`、
      危険を `size-4` に拡大し、`code_debt_score` に応じて `fill-opacity`（塗り濃度）をスケールさせ、
      件数チップ（プロット件数の表示）を添える。
- [ ] `frontend/src/lib/components/galaxy/star-node.svelte:10,28-29` — 星は固定 `size-3` で、
      KC（`file.kc`）は `style:opacity`（glow）にしか効いていない。KC に応じて**サイズもスケール**
      させ、理解度の高低をサイズでも表現する。
- [ ] `frontend/src/lib/components/galaxy/star-map.svelte:52` のワームホール `<svg>` は
      `viewBox="0 0 100 100"`、`frontend/src/lib/components/galaxy/star-system.svelte:10` の星は
      絶対配置の HTML（star-map.svelte:67-71）で、**両者は viewBox を共有していない**ため
      一緒にリフローできない。星とワームホールを**共有 viewBox（または共通座標系）**に載せ、
      ビューポート変化時に一緒にリフローするようにする。

### rank 30 — Galaxy のレスポンシブ化（中 / M / Galaxy）

- [ ] `frontend/src/routes/[org]/[project]/galaxy/+page.svelte:20` — `Tabs.Root value="map"` が
      ハードコードで、ビューポート判定が無い。`<768px` では `mastery-list`（`list` タブ）を
      デフォルトにする（`matchMedia` 等でビューポートに応じた初期タブ選択）。
- [ ] `frontend/src/routes/[org]/[project]/galaxy/+page.svelte:35` — `<StarMap>` を包む
      `min-h-0 flex-1` の div に **`min-width` 付き `overflow-auto` ラッパー**を足し、
      狭幅でマップが潰れず横スクロールできるようにする。
      （star-system.svelte:10 の `max-w-32 flex-wrap` で一部リフローはするが、ラップしたスクロール
      コンテナは未整備。）
- [ ] `frontend/src/lib/components/galaxy/star-map.svelte:52` — ワームホール `<svg>` の
      `preserveAspectRatio="none"`（縦横比を無視して歪ませている）を**外す**ことで、
      狭幅時のワームホール歪みを避ける（rank 20 の共有 viewBox 化と整合させる）。

### rank 33 — テーマトグル公開 + 無効ナビ項目のキーボード発見性（軽 / S / UserMenu・sidebar）

- [ ] `frontend/src/lib/components/shell/user-menu.svelte` — 現状は Label（email）+ ログアウト
      Item のみで、テーマトグルが UI から到達できない。`mode-watcher` の `setMode`
      （`mode-watcher@^1.1.0` 導入済み、ルートは `frontend/src/routes/+layout.svelte:6,12` で
      `<ModeWatcher defaultMode="dark" />` を使用）を用いたテーマトグル項目を DropdownMenu に追加する。
- [ ] `frontend/src/lib/components/shell/nav-item.svelte:27-34` — `!enabled` の項目が
      `href` も `aria-disabled` も無い非フォーカス可能な `<div>`（`text-muted-foreground/40`、~40% 不透明）
      でレンダリングされ、キーボードで発見できない。これを **`aria-disabled` 付きの
      フォーカス可能なリンク + Soon バッジ**に置き換える。
      （Soon バッジ配線自体は nav-item.svelte:53-54,71-72 に既存だが `item.comingSoon` を立てる項目が
      無く休眠中 — rank 1 連動。`m.shell_soon()`（`messages/ja.json:82` = `"soon"`）を流用する。）

## 対象外・保留

### rank 34 — モバイル Sheet の a11y（中 / S / mobile nav）— 主要部は実装済み（一部のみ任意フォロー）

監査結果 `valid=true / alreadyImplemented=true`。rank が挙げる主要な a11y ギャップ
（`sr-only` の `SheetTitle`）は**既に閉じている**ため、新規タスクには起こさない。

- `frontend/src/routes/[org]/+layout.svelte:28` に
  `<Sheet.Title class="sr-only">DevDebtOps</Sheet.Title>` が既に存在し、bits-ui が要求する
  タイトル要件を満たしている（文言は `Navigation` ではなく `DevDebtOps`）。
- Sheet は `Sheet.Trigger` ではなく `frontend/src/lib/components/shell/topbar.svelte:20-28` の
  プレーンな Button が `sidebar.mobileOpen = true` を立てて開く独自方式。

未確認で残る軽微な懸念（任意フォロー、本 issue 必須ではない）:
- ラベルの明確化として `DevDebtOps` → `Navigation`（または `m.*` メッセージ）への変更余地。
- **閉時にフォーカスがトップバーのメニューボタンへ戻るか**は未検証。Sheet を `Sheet.Trigger` 経由でなく
  カスタム `mobileOpen` で開いているため、bits-ui の自動フォーカス復帰が発火しない可能性がある。
  キーボード操作での確認を推奨するが、主要 a11y ギャップは既に解消済みのため保留扱いとする。

## 完了条件

- **色のみ符号化（rank 10）:** `black_hole` / `dim_star` が色を無視しても（グレースケール表示でも）
  グリフ / パターンで判別でき、`masteryDot` も同様に判別可能。危険ドットに `!` 等の非色マーカーが付く。
  優先度バッジが `aria-label`（優先度 + 2 軸値）を読み上げる。
- **focus-visible / キーボード（rank 11）:** 星 / 散布図ドットの双方が Tab フォーカスで
  可視リング（`focus-visible:ring-2`）を表示し、~24px のヒットターゲットを持つ。星はキーボード
  フォーカスでツールチップが開く（実機確認済み）。
- **reduced-motion（rank 16）:** OS の「視差効果を減らす」設定時、kc-meter の補間が即時化されつつ
  `+Xpt` は表示され、星 / 散布図ドットのホバー拡大が止まり、`layout.css` のグローバルルールで
  全般のトランジションが抑制される。
- **可読化（rank 20）:** 散布図ドットが `size-3`（危険 `size-4`）+ `code_debt_score` 連動の塗り濃度 +
  件数チップを持つ。星が KC に応じてサイズスケールする。星とワームホールが共有座標系で
  一緒にリフローする。
- **レスポンシブ（rank 30）:** `<768px` で Galaxy が `list` タブをデフォルト表示し、マップは
  `min-width` + `overflow-auto` で横スクロール可能、ワームホールが歪まない
  （`preserveAspectRatio="none"` 除去）。
- **テーマ / ナビ（rank 33）:** UserMenu からテーマを切り替えられ（`setMode`）、無効ナビ項目が
  `aria-disabled` のフォーカス可能リンク + Soon バッジとしてキーボードで発見できる。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` がパスすること
  （**バックエンド変更は無いため backend ゲートは対象外**）。

## 参考

### 元レビュー rank 対応

| rank | テーマ | 重要度 / 規模 | 本書での扱い |
|---|---|---|---|
| 10 | 色のみ符号化の解消 | 重大 / M | タスク化（star-node / galaxy-labels / debt-matrix / priority-badge） |
| 11 | focus-visible とキーボード操作 | 重大 / M | タスク化（star-node / debt-matrix、星 onclick 前提は現行で解消済み） |
| 16 | `prefers-reduced-motion` 尊重 | 中 / S | タスク化（layout.css / kc-meter / star-node / debt-matrix） |
| 20 | 可視化ノードの可読化 | 重大 / M | タスク化（debt-matrix / star-node / star-map + star-system 共有 viewBox） |
| 30 | Galaxy のレスポンシブ化 | 中 / M | タスク化（galaxy +page / star-map） |
| 33 | テーマトグル + 無効ナビ発見性 | 軽 / S | タスク化（user-menu / nav-item、rank 1 連動） |
| 34 | モバイル Sheet の a11y | 中 / S | **対象外・保留**（sr-only SheetTitle 実装済み、フォーカス復帰のみ任意確認） |

### 関連 file（現行実装・検証済み）

- 可視化ノード
  - `frontend/src/lib/components/galaxy/star-node.svelte` — 星ノード（button + Tooltip、size-3 固定 / glow のみ）
  - `frontend/src/lib/components/galaxy/star-system.svelte` — 星系（`max-w-32 flex-wrap` の HTML 配置）
  - `frontend/src/lib/components/galaxy/star-map.svelte` — ワームホール SVG（`viewBox 0 0 100 100` / `preserveAspectRatio="none"`）
  - `frontend/src/lib/components/galaxy/galaxy-labels.ts` — `masteryLabel` / `masteryDot`（純色ドット）
  - `frontend/src/lib/components/overview/debt-matrix.svelte` — 散布図ドット（button + focus tooltip、危険 ring 済み）
  - `frontend/src/lib/components/matrix/priority-badge.svelte` — 優先度バッジ（2 本ミニゲージ、`aria-hidden`）
  - `frontend/src/lib/components/quiz/kc-meter.svelte` — KC 補間メーター（無条件 Tween）
- App Shell / レイアウト
  - `frontend/src/routes/[org]/[project]/galaxy/+page.svelte` — Galaxy ページ（Tabs `value="map"` 固定）
  - `frontend/src/lib/components/shell/user-menu.svelte` — UserMenu（email + logout のみ）
  - `frontend/src/lib/components/shell/nav-item.svelte` — ナビ項目（`!enabled` は非フォーカス div）
  - `frontend/src/lib/config/nav.ts` — `NavItem.comingSoon` 定義済み・未使用
  - `frontend/src/routes/layout.css` — グローバルスタイルシート（reduced-motion 追加先）
  - `frontend/src/routes/+layout.svelte` — `<ModeWatcher defaultMode="dark" />`（mode-watcher 設置箇所）
  - `frontend/src/routes/[org]/+layout.svelte` — モバイル Sheet（rank 34 / 対象外）
  - `frontend/src/lib/components/shell/topbar.svelte` — モバイルメニューボタン（`sidebar.mobileOpen`）

### 規約

- `CLAUDE.md` — フロント = kebab-case、Svelte 5 runes のみ、shadcn-svelte@latest（`ui/` は読み取り専用 →
  ラッパーで `cn` 合成）、Tailwind v4（`tailwind.config.js` なし）、Paraglide 2.0（ja 主・en 従、
  `m.shell_soon()` 等）、`bun run check` / `bun run lint` / `bun run test:unit` ゲート。
- 「警告を無視しない」方針に従い、a11y 系の eslint / svelte-check 警告もエラー扱いで解消する。

### 関連 issue

- `docs/issue/013-settings-org-members-wiring.md` — クラスベース runes ストア / shadcn ラッパー / Paraglide の様式参照。
