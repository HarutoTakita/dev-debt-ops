# ADR 0006: 機能（feature）単位 KC ロールアップの集約方針

- ステータス: 採用（issue 055）
- 関連: [ADR 0003 KC mastery 閾値](./0003-kc-mastery-thresholds.md)、[ADR 0005 quiz KC](./0005-quiz-certified-kc.md)、issue 052（feature 写像）

## 背景

052 で機能↔ファイル写像（`feature_files`）が、053/054 で機能のクイズ KC が入った。Overview /
負債レジストリ / Galaxy をファイル単位固定から機能（feature）/ フォルダ（folder）/ ファイル（file）
の粒度切替に拡張するにあたり、ファイル KC を機能単位へロールアップする集約方針を確定する必要がある。

## 決定

機能ノードの値は、機能配下ファイル（`feature_files` の `file_path`）のファイル KC（`file_kc` 集計行
= authorship + quiz の max）から次のように算出する（MVP）:

- `knowledge_coverage(feature) = average( KC(file) )` — 大半が理解済みの機能は理解済みと読める。
- `weakest_file` = 最小 KC のファイル（**理解負債の焦点**）を併せて返す。最弱リンクの可視化は
  この `weakest_file` が担い、ヘッドライン KC は平均とする（1 ファイルの暗部で機能全体が
  過度に赤くならないバランス）。
- `code_debt_score(feature) = max( code_debt_score(file) )` — 既存のファイル集計と同じ max を流用
  （コード負債の本格的な機能ロールアップは issue 057）。
- `priority = derive_priority(code, knowledge_coverage)`（既存の 2 軸ロジックを再利用）。
- **folder** 粒度は `file_kc.module`（= ディレクトリ）射影。`feature` とは別物として API/フロントで明示する。

## 後方互換

`granularity` 未指定（既定 `file`）は従来のファイル単位挙動と完全互換。`feature`/`folder` のときも
`files`（ファイル単位の点）は常に返し、`features`（ロールアップノード）を追加で返す。

## 対象外

- コード負債の機能ロールアップ本実装（複雑度/重複/デッドの機能集約）→ 057。
- `confidence` 加重平均 / min ヘッドライン併記 → 将来（056 の表示要件と調整）。
- class / function 粒度の実計測 → 057（API 値だけ確保）。
