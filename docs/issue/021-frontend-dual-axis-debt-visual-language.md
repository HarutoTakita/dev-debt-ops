# 二軸負債のビジュアル＋数値言語を統一する

## 概要

Rosetta は「コード負債（amber）× 知識被覆 KC（teal）」という二軸を一級概念として扱うが、
KC の**数値表記**・KC の**色エンコーディング**・**警告トーン**・**語彙定義**・**i18n** が
画面ごとにバラバラに実装されており、同じ概念が複数の見た目・複数の数値フォーマットで現れている。
本 issue では「1 コンセプト 1 エンコーディング」を原則に、共通 KC フォーマッタ・統一カラーランプ・
専用警告トーン・二軸凡例・ハードコード日本語の多言語化を一つのシステムとして整える。
**バックエンド不要**（フロントエンドの表示層・トークン・文言のみ）。

## 背景・目的

Rosetta のデモ価値は「ファイルが二軸平面（コード品質 × チーム理解度 KC）のどこに居るか」が
一目で伝わることにある。ところが現状はその二軸の**視覚言語が統一されていない**：

- **KC の数値表記が 4 通り** — 生の float（`KC 0.62`）、四捨五入パーセント（`KC 62%`）、
  接頭辞なしパーセント（`62%`）が画面ごとに混在し、同じ KC が別物に見える。
- **KC の色がブランドトークンから駆動されていない** — Overview は `bg-debt-knowledge`（teal トークン）を
  使うのに、Galaxy は `cyan-300` / `teal-400` というパレット外のハードコード色を使い、
  `black_hole` は `bg-destructive` ではなく素の `red-500` を使う。「ティール = 知識」という規約が
  Galaxy で崩れている。
- **amber が二重の意味を持つ** — `--color-debt-code`（amber）は本来「コード負債軸の色」だが、
  priority/status バッジの段階表示にも流用され、「軸の色」と「警告の色」が衝突している。
- **二軸の語彙がどこにも定義されていない** — 「amber = コード負債 / teal = 知識被覆 KC」という
  軸そのものの凡例が無く、初見のユーザーは何を見ているか分からない。
- **ハードコード日本語が 2 件残る** — 散布図ツールチップと優先度バッジ title が Paraglide を通っておらず、
  英語ロケールでも日本語が出る。

これらを「1 コンセプト 1 エンコーディング」の下に束ねる：
**ティール = 知識（明るさ = 被覆度） / amber = コード負債軸 / 赤 = 危険専用** を
フォーマッタ・トークン・凡例・i18n の各層で一貫させる。

CLAUDE.md 規約に整合させる：Svelte 5 runes のみ、shadcn-svelte@latest（`ui/` は読み取り専用・ラッパーで合成）、
Tailwind v4（`@theme inline` トークン）、Paraglide 2.0（ja 主・en 従）、kebab-case ファイル名。

## タスク

### rank 5 — 共通 KC フォーマッタを導入し全 KC 表記を統一する

現状、KC は 4 通りの表記で描画されている（共通ヘルパは `src/lib/utils.ts` に `cn` しか無く、
`formatKc` / `formatMetric` は **grep で皆無**）：

- 生 float: `frontend/src/lib/components/matrix/kc-gauge.svelte:9`（`KC {value.toFixed(2)}`、
  ただし内部では :5 で四捨五入 pct を計算し :10 の `title` に使っているため表示と内部が不一致）
- 生 float: `frontend/src/lib/components/matrix/debt-meta-panel.svelte:17`（`debt.knowledge_coverage.toFixed(2)`）
  および `:39`（`KC {dev.coverage.toFixed(2)}` — 開発者カバレッジ、同パターン）
- 四捨五入 pct: `frontend/src/lib/components/galaxy/star-node.svelte:35`（`KC {Math.round(file.kc * 100)}%`）
- 四捨五入 pct: `frontend/src/lib/components/galaxy/star-system.svelte:16`（`KC {Math.round(system.kc * 100)}%`）
- 接頭辞なし pct: `frontend/src/lib/components/galaxy/mastery-list.svelte:39`（`{Math.round(f.kc * 100)}%`）
- 接頭辞なし pct: `frontend/src/lib/components/quiz/kc-meter.svelte:18`（`{Math.round(pct.current)}%`、Tween 値）
- 四捨五入 pct: `frontend/src/lib/components/overview/debt-matrix.svelte:81-83`（ツールチップ内 `KC {Math.round(...)}%`）

タスク：

- [ ] 共通フォーマッタを新設する（`frontend/src/lib/format/kc.ts` 等、kebab-case）。
      `0..1` の比率を受け取り `formatKc(value) -> "KC 62%"`（四捨五入・小数 0 桁・`KC ` 接頭辞）、
      接頭辞なしバリアント `formatKcPct(value) -> "62%"` を提供する
- [ ] `kc-gauge.svelte:9` のラベルを `formatKc(value)` に置換（生 float `toFixed(2)` をやめ、:10 の `title` 計算と一致させる）
- [ ] `debt-meta-panel.svelte:17`（debt KC 行）を `formatKc`/`formatKcPct` に置換
- [ ] `debt-meta-panel.svelte:39`（開発者カバレッジ `KC {dev.coverage.toFixed(2)}`）を同フォーマッタに置換
- [ ] `star-node.svelte:35`（Tooltip 内 KC）を `formatKc(file.kc)` に置換
- [ ] `star-system.svelte:16`（星系集計 KC）を `formatKc(system.kc)` に置換
- [ ] `mastery-list.svelte:39`（KC 列、接頭辞なし）を `formatKcPct(f.kc)` に置換
- [ ] `kc-meter.svelte:18`（Tween の `pct.current` を既に `* 100` 済み）を整合させる
      — `formatKc*` は `0..1` 入力前提のため、`pct.current / 100` を渡すか pct 用バリアントを用意する
- [ ] `debt-matrix.svelte:81-83`（ツールチップ KC）を `formatKcPct` に寄せる（rank 15 の Paraglide 化と併せて実施）

> バックエンド不要。`developer-avatar.svelte:33`（Tooltip 内 `KC {dev.coverage.toFixed(2)}`）も同パターンのため、
> フォーマッタ導入のついでに揃えると一貫性が増す（任意）。

### rank 9 — 知識カラー言語を `--color-debt-knowledge` から駆動する

Galaxy の星はブランド teal トークンではなくパレット外のハードコード色で描かれている。
`--color-debt-knowledge`（`frontend/src/routes/layout.css:180`、oklch teal）は Galaxy から一切参照されていない：

- `frontend/src/lib/components/galaxy/star-node.svelte:11-18`:
  `star = bg-cyan-300` / `dim_star = bg-teal-400/60` / `black_hole = border-red-500/80 bg-red-950` /
  `unexplored` = 破線 slate。星の発光は `file.kc` の `opacity`（:10, :28）で駆動し、色トークンは使っていない。
- `frontend/src/lib/components/galaxy/galaxy-labels.ts:14-19`（`masteryDot`）:
  `bg-cyan-300` / `bg-teal-400/70` / `bg-red-500`。`masteryDot` は `mastery-list.svelte:28` でも消費されるため両所同時更新になる。

対して Overview は正しく `bg-debt-knowledge` を使う（`debt-matrix.svelte:34,62` / `kc-gauge.svelte:11` / `kc-meter.svelte:20`）。
`cyan-300` はデザインパレットに存在せず（`layout.css` は teal/amber の 2 トークンのみ定義）、危険でない星に `red-500` が使われている。

タスク：

- [ ] `star-node.svelte:11-18` の `cls` マップを `--color-debt-knowledge` 駆動に置換：
      低 KC = 暗/淡、高 KC = 明るい teal の明度ランプにする（`bg-debt-knowledge` + opacity/brightness）。
      `cyan-300` / `teal-400` を撤去
- [ ] `black_hole` を危険専用トークンへ：素の `red-500`/`red-950` をやめ `bg-destructive`（危険専用）に寄せる
- [ ] `galaxy-labels.ts:14-19` の `masteryDot` を同じ規約に揃える（`star`/`dim_star` は teal ランプ、`black_hole` は destructive、`unexplored` は破線維持）。
      これにより `mastery-list.svelte:28` の凡例ドットも 1:1 で一致する
- [ ] 規約を「ティール = 知識 / 明るさ = 被覆度 / 赤（destructive）= 危険専用」に固定し、Galaxy と Overview のドット規約を一致させる

> バックエンド不要。色トークンとクラス定義のみの変更。

### rank 15 — ハードコード日本語 2 件を Paraglide 化する

Paraglide を通っていない生の日本語テンプレートリテラルが 2 件残る（両ファイルとも既に `import * as m from "$lib/paraglide/messages"` 済み）：

- `frontend/src/lib/components/overview/debt-matrix.svelte:80-84`:
  `· 品質 {Math.round((1 - hovered.code_debt_score) * 100)} / KC {Math.round(hovered.knowledge_coverage * 100)}%`
- `frontend/src/lib/components/matrix/priority-badge.svelte:22`:
  `title={`コード負債 ${Math.round(code * 100)} / 理解欠落 ${Math.round(know * 100)}`}`

`messages/ja.json` / `en.json` に `overview_tooltip_quality_kc` / `matrix_priority_title` キーは **存在しない**（grep で皆無）。

タスク：

- [ ] `frontend/messages/ja.json` にパラメータ付きキーを追加：
      `overview_tooltip_quality_kc`（`quality` / `kc` 数値パラメータ）、`matrix_priority_title`（`code` / `know` 数値パラメータ）
- [ ] `frontend/messages/en.json` に同キーの英語訳を追加（ja 主・en 従）
- [ ] `debt-matrix.svelte:80-84` を `m.overview_tooltip_quality_kc({ quality, kc })` に置換（rank 5 の `formatKcPct` と整合）
- [ ] `priority-badge.svelte:22` の `title` を `m.matrix_priority_title({ code, know })` に置換

> バックエンド不要。これら 2 件が指摘された唯一の生 JP 文字列。両方とも数値パラメータを取るため Paraglide のパラメータ化メッセージを使う。

### rank 19 — amber の二重意味を専用警告トーンで解消する

`--color-debt-code`（amber）が priority/status バッジの段階表示に流用され、「軸の色」と「警告の色」が衝突している。
`layout.css` には `--warning` トークンが**存在しない**（`--color-debt-code` / `--color-debt-knowledge` / `--color-success` / `--color-danger` のみ）：

- `frontend/src/lib/components/matrix/priority-badge.svelte:14`: P1 トーン = `bg-debt-code/15 text-debt-code`（amber を優先度段階に流用）
- `frontend/src/lib/components/matrix/debt-status-badge.svelte:10-11`: `in_pr` と `in_progress` がともに `bg-debt-code/15 text-debt-code`

一方 amber は軸可視化として正当に使われている（`weekly-activity.svelte:15`、`debt-trend-strata.svelte:18,31`、`debt-matrix.svelte:37`）ため、
バッジ段階だけを別トーンへ逃がす。

タスク：

- [ ] `frontend/src/routes/layout.css` の `@theme` に専用警告トークン `--color-warning`（amber 近傍だが debt-code とは別）を追加する
      （既存 `--color-debt-code:179` / `--color-debt-knowledge:180` の隣）
- [ ] `priority-badge.svelte:14` の P1 トーンを `bg-warning/15 text-warning` 等の警告トーンに置換
- [ ] `debt-status-badge.svelte:10-11` の `in_pr` / `in_progress` を同じ警告トーンに置換
- [ ] `--color-debt-code`（amber）は**軸可視化専用**に限定（散布図/地層/weekly-activity はそのまま維持）。
      P0/open の `bg-destructive` 系・`bg-success` 系は変更しない

> バックエンド不要。`debt-code` はおよそ 19 ファイルで使われるが、過負荷なのは priority/status の段階用途のみ。軸用途は据え置き。

### rank 22 — 二軸の入門解説／語彙定義を追加する

「amber = コード負債 / teal = 知識被覆 KC」という**軸そのもの**の凡例・語彙が存在しない。
`quadrant-legend.svelte` は 4 象限の名前/物語を色ドットで説明するが、軸の色語彙は定義していない
（しかも `code_repay` ドットが `bg-debt-knowledge`、`refactor` ドットが `bg-debt-code` と象限中心で、軸語彙ではない）。
Galaxy ページ（`frontend/src/routes/[org]/[project]/galaxy/+page.svelte:28`）には `m.galaxy_my_kc(): {galaxy.myKc}%` の
KC 表示はあるが、info アイコンによる語彙解説アフォーダンスは無い。

タスク：

- [ ] 小さな再利用可能な軸凡例/ツールチップコンポーネントを新設する（`ui/` 外、例 `frontend/src/lib/components/overview/axis-legend.svelte`）：
      「コード負債（amber）/ 知識被覆 KC（teal）」をドット + ラベルで提示。
      shadcn `Tooltip` は既に利用可能（`star-node` / `developer-avatar` で使用中）
- [ ] Overview マトリクスタイトル横（`debt-matrix.svelte:20` の `m.overview_matrix_title()` 付近、`overview-dashboard.svelte:27` で描画）に
      info アイコン → 軸凡例を表示する
- [ ] Galaxy の KC 表示（`galaxy/+page.svelte:28`）隣に info アイコンを置き、同じ軸凡例を表示する
- [ ] 凡例の amber/teal ドット規約は rank 9 の統一ティール・rank 5 の `formatKc` と 1:1 で一致させる
- [ ] 凡例ラベルは Paraglide 化（`messages/ja.json` / `en.json` に軸語彙キーを追加、ja 主・en 従）

> バックエンド不要。新規 UI。rank 5（formatKc）・rank 9（統一 teal）とセットで実施し、ドット規約を一致させる。

### rank 31 — wormhole / 象限 / アバター状態にインラインの意味付与

3 つのサブターゲットを確認済み：

- **象限ラベルのコントラスト/サイズ**: `frontend/src/lib/components/overview/debt-matrix.svelte:41-54`。
  4 象限ラベルは 10px の `text-muted-foreground` で低コントラスト。危険ラベル（:49）だけ `font-semibold text-destructive` で強調済み。
  残り 3 つ（code_repay :44 / ideal :46 / refactor :52）が弱い。
- **wormhole のホバーハイライト + 方向矢印**: `frontend/src/lib/components/galaxy/star-map.svelte:53-63`。
  現状は素の破線（`stroke-dasharray="1 1.2"`、静的 rgba）で、方向矢印もホバーハイライト/ミュートも無い。
- **アバター緑/破線のインラインキー**: 緑/破線エンコーディングは `frontend/src/lib/components/matrix/developer-avatar.svelte:23-25`
  （`border-success` vs `border-dashed`）にあり、意味キーは Tooltip（:32-34）のみ。
  アバタースタックを並べる `frontend/src/lib/components/matrix/debt-list-row.svelte:30-34` と
  `frontend/src/lib/components/matrix/debt-meta-panel.svelte:32-43` の両方にインラインの緑/破線キーが無い。

タスク：

- [ ] `debt-matrix.svelte:41-54` の弱い 3 象限ラベル（code_repay/ideal/refactor）のコントラスト/サイズを上げる
      （危険ラベル :49 の強調と釣り合うトーンに）
- [ ] `star-map.svelte:53-63` の wormhole に from→to の方向矢印（SVG `marker`）と、線ごとのホバーハイライト＋他線ミュートを追加する
- [ ] `debt-list-row.svelte:30-34` のアバタースタックに緑/破線の 1 行インラインキーを添える
- [ ] `debt-meta-panel.svelte:32-43` のアバタースタックにも同じインラインキーを添える
- [ ] キーの文言は Paraglide 化（`messages/ja.json` / `en.json`、ja 主・en 従）

> バックエンド不要。象限ラベルはクラス調整、wormhole は SVG 拡張（net-new）、アバターキーは新規インライン表示。

## 完了条件

- KC を表示する全箇所（`kc-gauge` / `debt-meta-panel` ×2 / `star-node` / `star-system` / `mastery-list` /
  `kc-meter` / `debt-matrix` ツールチップ）が共通 `formatKc` / `formatKcPct` を経由し、
  同じ KC 値が同じ表記（`KC 62%` 形式）で表示されること。生の `toFixed(2)` 表示が残っていないこと。
- Galaxy の星・`masteryDot` が `--color-debt-knowledge` 由来の teal 明度ランプで描画され、`cyan-300` / `teal-400` /
  素の `red-500` がコードベースから消え、`black_hole` のみ `destructive`（危険専用）を使うこと。
  Galaxy と Overview のドット色規約が一致すること。
- 英語ロケールで散布図ツールチップと優先度バッジ title が英語表示になり、ハードコード日本語が残っていないこと
  （`overview_tooltip_quality_kc` / `matrix_priority_title` が ja/en 両方に存在）。
- `--color-warning` トークンが導入され、priority-badge P1 と debt-status-badge `in_pr`/`in_progress` が警告トーンを使い、
  `--color-debt-code`（amber）は軸可視化（散布図/地層/weekly-activity）のみに残ること。
- Overview マトリクスタイトル横と Galaxy KC 表示隣の info アイコンから「コード負債（amber）/ 知識被覆 KC（teal）」の
  軸凡例が表示され、そのドット規約が Galaxy 凡例と一致すること。
- 象限ラベル 4 つが読めるコントラスト/サイズになり、wormhole が from→to 矢印 + ホバーハイライトを持ち、
  list/detail 両方のアバタースタックに緑/破線のインラインキーが付くこと。
- `cd frontend && bun run check` / `bun run lint` / `bun run test:unit` がパスすること。
- `CHANGELOG.md`（日本語）に `Changed`（KC 表記/カラー言語の統一）/ `Added`（軸凡例・警告トークン）の追記。

## 参考

- 元レビュー rank 対応
  - rank 5 → 共通 KC フォーマッタ（`formatKc` / `formatKcPct`）
  - rank 9 → 知識カラー言語統一（`--color-debt-knowledge` 駆動）
  - rank 15 → ハードコード日本語 2 件の Paraglide 化
  - rank 19 → amber 二重意味の解消（`--color-warning` 導入）
  - rank 22 → 二軸の入門解説/語彙定義（軸凡例 + info アイコン）
  - rank 31 → wormhole / 象限 / アバター状態のインライン意味付与
- 関連 file（改修対象）
  - `frontend/src/lib/utils.ts` — 現状ヘルパは `cn` のみ。`formatKc` 等の置き場は別モジュール推奨
  - `frontend/src/routes/layout.css:175-181` — `@theme` 二軸トークン（`--color-debt-code` / `--color-debt-knowledge`）。`--color-warning` 追加先
  - `frontend/src/lib/components/matrix/kc-gauge.svelte` / `debt-meta-panel.svelte` / `priority-badge.svelte` / `debt-status-badge.svelte` / `developer-avatar.svelte` / `debt-list-row.svelte`
  - `frontend/src/lib/components/galaxy/star-node.svelte` / `galaxy-labels.ts` / `star-system.svelte` / `mastery-list.svelte` / `star-map.svelte`
  - `frontend/src/lib/components/overview/debt-matrix.svelte` / `quadrant-legend.svelte` / `overview-dashboard.svelte`
  - `frontend/src/lib/components/quiz/kc-meter.svelte`
  - `frontend/src/routes/[org]/[project]/galaxy/+page.svelte` — KC 表示（:28）。info アイコンのアンカー
  - `frontend/messages/ja.json` / `frontend/messages/en.json` — Paraglide 文言（ja 主・en 従）
- 規約
  - `CLAUDE.md` — フロント kebab-case、Svelte 5 runes のみ、`ui/` は読み取り専用（ラッパーで `cn` 合成）、
    Tailwind v4 `@theme inline` トークン、Paraglide 2.0、`bun run check` / `lint` / `test:unit` ゲート
