# クラス / 関数粒度を AST 解析で計測・配信・表示する

> 親トラッキング: [057 多粒度計測の拡張](./057-multi-granularity-code-debt-rollout.md)（B）から切り出し。

## 概要

`Granularity.CLASS` / `FUNCTION` は 052 で値だけ定義され、056 の UI では disabled の将来枠。
本 issue は AST 解析でクラス / 関数の範囲を抽出し、シンボル単位の KC・コード負債を計測・配信・表示する。

## 残タスク

- [ ] 言語別パーサで AST からクラス / 関数の範囲（開始-終了行）を抽出する解析層を新設
      （正規表現ベースの `code_analysis.py` を超える。Python/TS-JS 優先、言語追加可能な抽象）。
- [ ] シンボル単位 KC: blame の行範囲をシンボル範囲へマッピングして KC(symbol, dev) を算出（029 の拡張）。
- [ ] シンボル単位コード負債: 複雑度 / 重複をシンボル単位で算出（028 の拡張）。
- [ ] `granularity=class|function` の集計・配信（055 の拡張）と、056 の disabled 解除（UI 有効化）。

## 完了条件

- クラス / 関数粒度でコード負債・理解負債が計測・配信・表示でき、056 の class/function が選択可能になる。
- バックエンド/フロントのゲートが通る。

## 参考
- `backend/service/service/services/code_analysis.py`、`backend/service/service/pipelines/kc_analysis.py`、
  052（`Granularity`）、055（粒度配信）、056（粒度 UI）、057。
