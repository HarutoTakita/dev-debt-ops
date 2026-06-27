# フロント：粒度切替 UI と機能（feature）単位の理解負債表示を実装する

## 概要
ダッシュボード（Overview マトリクス / Galaxy）に **粒度切替**（機能 / フォルダ / ファイル）を追加し、
055 の `granularity` API を消費して**機能単位の理解負債**を表示する。機能を 1 点/1 ノードとして描き、
機能 → ファイルのドリルダウンで配下を展開できるようにする。クラス/関数は将来枠として UI に出すが選択不可（disabled）。

## 背景・目的
- 現状の表示はファイル単位固定（`debt-matrix.svelte` の散布図 / Galaxy の星系=ディレクトリ）。ユーザーは
  「機能単位 / フォルダ単位 / ファイル単位…」と**粒度を切り替えて**負債を俯瞰したいが、切替 UI が無い。
- まず「機能単位の理解負債」を可視化することで、単独開発/PM でもクイズ（054）で埋めた機能 KC を一望できる。
- 機能 ≠ フォルダ である点を UI 上で明確に区別する（055 でも別物として配信される）。

## タスク

### A. 粒度切替 UI
- [ ] Overview / Galaxy 上部に粒度セグメント（機能 / フォルダ / ファイル）を追加。選択を URL クエリ or ストアで保持。
- [ ] `class` / `function` は項目として表示するが `disabled` + 「Coming soon（057）」ツールチップ。
- [ ] 選択粒度を `client.ts` の各取得関数へ `granularity` として渡す（055 のパラメータ）。

### B. 機能単位の表示
- [ ] `debt-matrix.svelte`（散布図）で `granularity=feature` のとき機能を 1 点として描画（点ラベル=機能名、サイズ=`file_count` 等）。
      既存の `pct()` クランプ（047）と二軸（code_debt_score × knowledge_coverage）をそのまま流用。
- [ ] 機能点クリックで**ドリルダウン**（機能 → 配下ファイルの散布図 / 一覧）。`GET .../features/{feature_key}` を消費。
- [ ] Galaxy で `granularity=feature` のとき「星系 = 機能」を描画（既存 force-layout / star-map を流用、ディレクトリ星系は `folder`）。
- [ ] 機能ごとの mastery / 理解負債バッジ（star/dim_star/black_hole）と「ベースラインクイズ未受験」状態の導線（054/クイズへ）。

### C. スキーマ / 契約 / 整合
- [ ] `frontend/src/lib/api/schemas.ts` に `featureDebtSchema` 等を追加（snake_case 維持で 055 の配信を Zod 解析）。
- [ ] i18n（Paraglide、ja/en）に粒度ラベル・機能ビューの文言を追加。
- [ ] 空状態（機能未クラスタリング / ベースライン未受験）と読み込み/エラー状態（023 の方針）を機能ビューにも適用。
- [ ] [049] の解析完了オートリフレッシュを機能クラスタリング（052）/ ベースライン（054）完了にも配線する。

## 完了条件
- Overview / Galaxy で粒度を「機能 / フォルダ / ファイル」に切り替えられ、機能単位の理解負債が表示される。
- 機能点/星系から配下ファイルへドリルダウンできる。
- 機能 ≠ フォルダ が UI 上で区別される。`class`/`function` は disabled で将来枠と分かる。
- 機能未クラスタリング / ベースライン未受験の空状態と、クイズ受験への導線が出る。
- フロント：`bun run check`（svelte-check、警告ゼロ）/ `bun run lint` / `bun run test:unit` が通る。
- `CHANGELOG.md`（日本語）に `Added`（粒度切替 + 機能単位理解負債表示）を追記。

## 技術詳細
- 既存：`frontend/src/lib/components/overview/debt-matrix.svelte`（`pct()` クランプ、二軸散布図）、
  `frontend/src/lib/components/galaxy/star-map.svelte` / `galaxy-graph.ts` / `force-layout.ts`（050）、
  `frontend/src/lib/api/client.ts`（取得関数）、`frontend/src/lib/api/schemas.ts`（Zod 契約）、
  `frontend/src/lib/stores/analysis-run-refresh.svelte.ts`（049 オートリフレッシュ）。
- 規約：Svelte 5 runes のみ、shadcn-svelte（`ui/` は読み取り専用、ラッパーで合成）、kebab-case ファイル、
  `Map`/`Set` は `.svelte` 内で eslint `prefer-svelte-reactivity` に触れるため計算ロジックは `.ts` に切り出す（050 の前例）。

## 対象外・保留
- **コード負債の粒度切替**（機能/フォルダのコード負債集計表示）→ 057（本 issue は理解負債の機能表示が主眼。code はバックエンド 055 の暫定値を流用表示）。
- **クラス/関数粒度の表示** → 057。
- **機能の人手編集 UI**（`source="manual"`）→ 将来。

## 参考
- 関連 issue：[055 機能単位集計 API](./055-backend-feature-granularity-debt-aggregation-api.md)、
  [054 機能ベースラインクイズ](./054-backend-initial-feature-baseline-quiz.md)、
  [047 マトリクス軸スケーリング](./047-overview-debt-matrix-axis-scaling.md)、
  [050 Galaxy 依存グラフ](./050-galaxy-code-dependency-graph.md)、
  [051 ナビ/IA 再編](./051-nav-ia-restructure-agents-learning-quiz.md)、
  [057 多粒度・コード負債拡張](./057-multi-granularity-code-debt-rollout.md)。
- 想定ラベル：`feature`, `frontend`。
