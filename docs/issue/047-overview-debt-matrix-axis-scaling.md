# 二軸負債マトリクスの軸スケーリング/データ不正を修正する

## 概要
観測台の二軸負債マトリクス（散布図）で、**コード負債（code_debt）の値が最大か最小に張り付き**、点が左右端のどちらかに偏って表示される。連続値であるべき軸が二値的に見え、二軸（コード負債 × 知識被覆）の分布が読み取れない。

## 背景・目的
このマトリクスは DevDebtOps の看板可視化。点が端に張り付くと「どのファイルがどの程度の負債か」という核心が伝わらない。軸の値が連続的に分布し、四象限（危険/重点学習/技術改善/安全）が意味を持つ状態にする必要がある。

## タスク
- [ ] **データソースを切り分ける**: モック（`frontend/src/lib/mock/overview-mock.ts`）使用時と実 API（`getOverview`）使用時のどちらで症状が出るか確認する。モックは連続値（`code_debt_score` 0.58〜0.90）なので、実 API の値が二値/極端になっていないか検証する。
- [ ] バックエンドの Overview 集計（`backend/api/app/...` の overview/debt 集計サービス）が返す `code_debt_score` / `knowledge_coverage` が **0〜1 の連続値**で正規化されているか確認し、二値化・丸め・誤った最大値除算があれば是正する。
- [ ] 軸の対応関係を確認する: 現状 `debt-matrix.svelte` は `left = knowledge_coverage`、`top = code_debt_score`。ユーザー観測（コード負債が「左右端」で max/min）と食い違うため、**軸の取り違え/反転**が無いか検証する。
- [ ] フロント側の座標マッピング（`debt-matrix.svelte`）に正規化・クランプの問題が無いか確認し、必要ならデータ範囲に応じたスケーリングを導入する。
- [ ] 点が密集して重なる場合に分布が潰れて見える問題（不透明度・サイズ）も併せて見直す。
- [ ] ツールチップの「品質」表示（`1 - code_debt_score`）が実値と整合するか確認する。

## 完了条件
- 実 API データで、コード負債・知識被覆がともに **0〜1 の連続値**として散布図に分布する（端に張り付かない）。
- 軸（左右＝知識被覆、上下＝コード負債、もしくは仕様で定めた向き）が定義どおりで、四象限が意味を持つ。
- ツールチップの数値が点の位置と一致する。

## 技術詳細
- 位置計算: `frontend/src/lib/components/overview/debt-matrix.svelte:87` `style="left: {f.knowledge_coverage * 100}%; top: {f.code_debt_score * 100}%;"`（正規化・クランプ無しの直接マッピング）。
- 不透明度: 同 `:88` `0.45 + f.code_debt_score * 0.55`。
- ツールチップ: 同 `:111` `quality: Math.round((1 - hovered.code_debt_score) * 100)`。
- モック（連続値・参考）: `frontend/src/lib/mock/overview-mock.ts:35-36`。
- 仮説: 実 Overview API の `code_debt_score` が二値（0/1）または丸めで極端化している可能性が高い。座標式自体は妥当のため、**データソース（API 集計）側が第一容疑**。

## 参考
- 関連: [007 観測台 二軸負債マトリクス](./007-overview-debt-matrix-dashboard.md)、[031 Overview 二軸集計 API](./031-backend-overview-and-debt-registry-api.md)、[028 コード負債検知](./028-backend-code-debt-detection-pipeline.md)
- 想定ラベル: `bug`, `frontend`, `backend`
