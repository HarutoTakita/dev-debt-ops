# コード負債の粒度集計を本実装する（機能/フォルダ、code_debts 直接集計）

> 親トラッキング: [057 多粒度計測の拡張](./057-multi-granularity-code-debt-rollout.md)（A）から切り出し。

## 概要

055 は理解負債（KC）を機能/フォルダへロールアップしたが、**コード負債は配下ファイルの
`code_debt_score` の max を流用**するに留まった。本 issue はコード負債
（複雑度 / 重複 / デッド）の機能・フォルダ単位の**本格的な集計**を実装する。

## 残タスク

- [ ] `code_debts` 行を機能（`feature_files` 経由）/ フォルダ（`module`）へ直接集計（件数・type 別内訳・
      severity 分布・合計 `estimated_repay_hours` 等）。max 流用ではなく集計指標を `FeatureDebtOut`（or 拡張）に載せる。
- [ ] Overview / マトリクスの粒度別コード負債軸（056 のコード負債側の深化。点サイズ/色を集計指標で駆動）。
- [ ] 集約方針（max / 件数 / 加重）を本 issue / 実装コメントに明記。

## 完了条件

- 機能 / フォルダ単位でコード負債が KC と同じ粒度で集計・配信・表示される。
- 既存のファイル単位挙動は後方互換。バックエンド/フロントのゲートが通る。

## 参考
- `backend/api/app/services/debt_query.py`（`_node_from_files` / `build_overview`）、`code_debts`、
  `feature_files`、057 / 055。
