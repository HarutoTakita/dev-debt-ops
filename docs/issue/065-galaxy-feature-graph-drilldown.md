# 理解度マップを「機能グラフ → 機能内ファイルグラフ」の 2 段ドリルダウンに再設計する

## 概要

現在の理解度マップ（Galaxy）は、ファイルを `module=ディレクトリ` で「星系（島）」にまとめ、島の中にファイル星ノードを並べる**入れ子構造**で、「グループの中にファイルがある」のが分かりにくい。

本 issue は次の 2 段ビューに再設計する：

1. **第一ビュー（機能グラフ）**: **機能（feature）を最小ノード**とし、**機能間のつながり**をグラフ（ノード＝機能、辺＝機能間依存）で表す。
2. **ドリルダウン（機能内ファイルグラフ）**: 機能ノードをクリックすると、その機能を構成する**ソースファイルの依存グラフ**にズームインする。「← 戻る」で第一ビューへ。

## 背景・目的

### 現状

- バックエンド `galaxy_query.build_galaxy`（`backend/api/app/services/galaxy_query.py`）は `file_kc`（集計行）と `dependency`（ファイル→ファイル）から、`_module_of`（ディレクトリ）で星系を作り、`PersonalGalaxyOut{ systems[], wormholes[] }` を返す。**機能レベルは無い。**
- フロント `star-map.svelte` / `galaxy-graph.ts` / `force-layout.ts` は、wormhole を**モジュール単位の辺**に集約し、モジュールノードを力学配置。各モジュールは `star-system.svelte` の「島」として描画し、中にファイル星（`star-node.svelte`）を並べる（＝入れ子）。
- 機能↔ファイル写像（`features`/`feature_files`、issue 052）と機能 KC ロールアップ（issue 055）はあるが、**Galaxy はまだ機能を使っていない**（055/056/057 で Galaxy 粒度は後送り）。

### 目的

1. 機能を第一級ノードにし、機能間の関係を一望できるようにする（入れ子をやめる）。
2. 機能をクリックして、その機能の内部構造（ファイル依存）へズームインできるようにする。
3. データは既存の `features`/`feature_files`/`dependency`/`file_kc` から導出（新規計測は不要）。

## 設計

### バックエンド — Galaxy 応答に機能レベルを追加（`galaxy_query` 拡張）

`build_galaxy` を拡張し、最新 `feature_clustering` run の `features`/`feature_files` を読み込んで以下を追加する（既存の `systems`/`wormholes` は Level 2 のファイル描画にそのまま使うため維持）：

- `features: list[FeatureNode]` — `{ key, name, kc, mastery, file_count }`。`kc` は機能配下ファイル KC の集約（055 と整合：平均、`mastery` は閾値適用）。
- `feature_edges: list[{ from, to }]` — `dependency`（file→file）を `feature_files` で機能へ写像し、**機能をまたぐ辺**のみを重複排除して列挙（from/to は feature key）。
- 各ファイル（`FileMasteryOut`）に `feature_key: str | None` を付与 → フロントが Level 2 で「その機能のファイル＋ファイル間 wormhole」を絞り込めるようにする。

> 単一エンドポイント（`GET .../galaxy`）の応答を拡張する方針（1 fetch で両レベルを賄う。ファイル/依存は既に全件返している）。機能未クラスタリング時は `features=[]`・`feature_edges=[]` で従来表示にフォールバック。

### フロント — 2 段ビュー（`star-map.svelte` 改修 + グラフ構築）

- **Level 1（既定）**: `features` をノード、`feature_edges` を辺として `force-layout` で配置。ノードは機能 1 つ＝1 円（ラベル＝機能名、色＝KC/mastery、次数リングは既存流用）。**島＋ファイル入れ子はやめる。**
- **Level 2（機能クリック）**: 選択機能の `feature_key` でファイルを絞り（`fileMastery.feature_key`）、その集合内の wormhole だけで `force-layout`。ファイル星（`star-node`）＋ファイル間の辺を描画。上部に「← {機能名}」のパンくず/戻る。
- `galaxy-graph.ts`: `buildFeatureGraph(features, feature_edges)`（neighbors/degree）と `buildFileSubgraph(galaxy, featureKey)`（ファイル＋絞り込み wormhole）を追加。`force-layout` は両レベルで再利用。
- `galaxy-store`: `selectedFeatureKey: string | null` を保持。`star-system.svelte` の入れ子島は Level 1 では不使用に（Level 2 のファイル描画へ転用 or 整理）。
- i18n（ja/en）: 戻る/パンくず・空状態（機能未クラスタリング）文言。

### 相互作用
- 機能クリック → `selectedFeatureKey` 設定 → Level 2 へズーム（同一キャンバスを差し替え + 戻る導線）。**※ドリルダウンの見せ方（インプレース・ズーム / サイドドロワー）は実装時に確定。**

## タスク

### backend
- [ ] `galaxy_query`: 機能ノード（KC 集約・mastery）+ 機能間辺（`dependency`×`feature_files` 写像・重複排除）+ ファイルへの `feature_key` 付与を追加。最新 `feature_clustering` run を参照。
- [ ] `schemas/galaxy.py` / `personalGalaxySchema`（フロント）: `features` / `feature_edges` / `fileMastery.feature_key` を追加（後方互換で nullable / 既定空）。
- [ ] test（api）: 機能間辺が機能をまたぐ依存のみ・重複排除されること。機能 KC が配下集約と一致。未クラスタリング時のフォールバック。

### frontend
- [ ] `schemas.ts`: `featureNodeSchema` / `feature_edges` / `fileMastery.feature_key` を追加。
- [ ] `galaxy-graph.ts`: `buildFeatureGraph` / `buildFileSubgraph` を追加（`force-layout` 再利用）。
- [ ] `star-map.svelte`: Level 1（機能グラフ）/ Level 2（機能内ファイルグラフ）の 2 モード + クリックでズーム + 戻る。入れ子島描画を Level 1 から撤去。
- [ ] `galaxy-store`: `selectedFeatureKey` 管理。i18n・空状態・049 オートリフレッシュ整合。
- [ ] test（vitest）: 機能クリックで Level 2 に切替・戻るで Level 1・サブグラフが当該機能のファイル/辺のみ。

## 完了条件
- 第一ビューが**機能ノード + 機能間グラフ**になり、入れ子（島の中のファイル）が無くなる。
- 機能クリックで**その機能のファイル依存グラフにズームイン**でき、戻れる。
- データは既存テーブルから導出（新規パイプライン不要）。未クラスタリング時もエラーにならずフォールバック。
- フロント：`bun run check`（警告ゼロ）/ `lint` / `test:unit`、バックエンド：ruff/ty/pytest が通る。
- `CHANGELOG.md`（日本語）に `Changed`（Galaxy を機能グラフ + ドリルダウンへ再設計）を追記。

## 対象外・保留
- 機能間辺の重み付け（依存本数で太さ）等の高度化は将来（MVP は有無のみ）。
- 機能クラスタリング自体の改善（052/精度）。
- クラス/関数粒度のグラフ（057/061）。

## 参考
- backend: `backend/api/app/services/galaxy_query.py`（`build_galaxy` / `_module_of`）、`backend/api/app/api/v1/galaxy.py`、`backend/api/app/schemas/galaxy.py`、`backend/shared/shared/models/{dependency,feature,feature_file,file_kc}.py`。
- frontend: `frontend/src/lib/components/galaxy/{star-map,star-system,star-node}.svelte` / `galaxy-graph.ts` / `force-layout.ts`、`frontend/src/lib/stores/galaxy-store.svelte.ts`、`frontend/src/routes/[org]/[project]/galaxy/+page.svelte`、`frontend/src/lib/api/schemas.ts`。
- 関連 issue: [052](./052-backend-measurement-granularity-and-feature-model.md) / [055](./055-backend-feature-granularity-debt-aggregation-api.md) / [056](./056-frontend-granularity-switch-and-feature-debt-view.md) / [057](./057-multi-granularity-code-debt-rollout.md)。
- 規約: `CLAUDE.md`（Svelte 5 runes・`Map`/`Set` は `.ts` に切り出し（eslint）・shadcn `ui/` 読取専用・snake_case 配信・i18n ja/en・CHANGELOG 日本語・ゲート）。
