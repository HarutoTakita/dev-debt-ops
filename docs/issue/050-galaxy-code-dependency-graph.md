# ギャラクシーのマップを実コード依存グラフのレイアウトにする

## 概要
ギャラクシーの「マップビュー」は、スター（モジュール/ファイル）を**ハードコードされた固定座標**（26 スロットを剰余で割り当て）に配置し、その上に実依存エッジ（wormhole）を描いている。エッジ自体は実コードの import 由来だが、配置が依存構造を反映しないため**つながりが読み取れない**。配置を実依存グラフに基づくレイアウト（力学/階層など）に置き換え、コードの依存構造を可視化する。

## 背景・目的
依存エッジは正しく抽出されているのに、ノード配置が恣意的なため線が交差・錯綜して意味を成さない。「どのモジュールが中心か」「どこに密結合があるか」を読めるようにすることで、ギャラクシーが知識被覆と依存構造の両方を見せる価値ある画面になる。

## タスク
- [ ] ノード配置を固定座標から**依存グラフに基づくレイアウト**に変更する（力学レイアウト or 階層レイアウト。`star-map.svelte` の `POS`/`posOf` を置換）。SPA・自己完結のため軽量な実装方針を決める（外部 CDN 不可なら自前 or バンドル済みライブラリ）。
- [ ] 粒度を選べるようにする: 現状はモジュール間に集約。**ファイル粒度の依存**も描けるよう、必要なら API を拡張する（後述）。
- [ ] エッジの可読性向上: ホバーで関連エッジのみ強調・他を減衰、方向（from→to）の矢印、自己/同一モジュールエッジの扱いを整理（`star-map.svelte:21-42` の現ロジックを土台に）。
- [ ] KC（マスター度）の色とノードサイズ（依存次数など）を両立させ、二重符号化が破綻しないよう凡例を更新。
- [ ] 大規模リポジトリでの描画（ノード/エッジ数が多い場合）の間引き・ズーム/パンや、`<768px` ではリスト表示へフォールバックする方針を決める。
- [ ] （API 拡張・必要時）ファイル粒度の依存を取得するエンドポイント `GET .../dependencies` を追加し、`dependencies` テーブルの file-to-file エッジを配信する。

## 完了条件
- マップ上のノード配置が実依存関係を反映し、依存の「つながり」が視覚的に追える。
- ホバー等でエッジ関係が明確になり、中心的モジュール/密結合が読み取れる。
- KC 色・凡例と両立し、レスポンシブ（狭幅はリストへ）でも破綻しない。

## 技術詳細
- 現状の固定配置: `frontend/src/lib/components/galaxy/star-map.svelte:8-18`（`POS` 26 スロット、`posOf` は index の剰余で割当）。
- エッジ描画（実依存・モジュール集約）: 同 `:21-42`（`galaxy.wormholes` から module ペアを解決し SVG 線を生成）。
- 依存抽出（バックエンド・実 import 解析）: `backend/service/service/services/dependency_extraction.py:135-163`（Python/JS/TS の import を解決し intra-repo エッジを返す）。
- 保存先: `dependencies` テーブル（`run_id` / `from_path` / `to_path`、`backend/api/app/alembic/versions/0008_*`）。
- 取得経路: `GET /api/v1/orgs/{slug}/projects/{project_slug}/galaxy`（`wormholes[]` を含む、`backend/api/app/api/v1/galaxy.py:26-41`）。ファイル粒度が必要なら別エンドポイントを追加。
- 制約: SPA は外部ホストへ通信不可。グラフ描画は自前実装かバンドル済みライブラリで行う。

## 参考
- 関連: [009 Knowledge Galaxy](./009-knowledge-galaxy-2d-map.md)、[027 GitHubGitClient 依存抽出](./027-backend-github-history-client-extension.md)、[029 KC 算出（dependencies 含む）](./029-backend-kc-knowledge-coverage-pipeline.md)、[048 ギャラクシー KC 是正](./048-galaxy-kc-all-mastered-fix.md)
- 想定ラベル: `feature`, `frontend`, `backend`
