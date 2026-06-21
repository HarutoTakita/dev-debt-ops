# ADR 0005: クイズ採点による KC 認定（`certified_via="quiz"`）

- ステータス: 採用（issue 053）
- 関連: [ADR 0003 KC mastery 閾値](./0003-kc-mastery-thresholds.md)、issue 029（KC 算出）、issue 034（クイズ採点）

## 背景

KC（Knowledge Coverage）は git blame の authorship からのみ算出され、`certified_via="authorship"`
は **上限 0.6**（`_AUTHORSHIP_KC_CEILING`）でキャップされる（issue 048 — 「書いた量 ≠ 理解」）。
このため (1) 単独開発（全行 1 人）や (2) コードを書かない PM/レビュアの理解が KC に反映されず
star に到達できない。クイズ基盤（034）は採点まで実装済みだが、採点結果を `file_kc` へ反映する
フックが未実装だった。

## 決定

クイズ採点完了時（`quiz_grading.process` 末尾）に、受験者 × 対象ファイルの KC を
`certified_via="quiz"` で `file_kc` に upsert する。

1. **スコア → KC 写像（MVP）:** `kc_quiz = quiz_score`（採点スコア 0..1 をそのまま認定 KC とする）。
2. **blame 非依存・上限なし:** authorship の 0.6 上限を quiz には適用しない（合格すれば star ≥0.7 到達可）。
3. **採用値:** 同一 `(run, file, dev)` について `kc = max(既存KC, kc_quiz)`。quiz が勝つとき
   `certified_via="quiz"`、そうでなければ既存の certified_via を保持（**KC を下げない**）。
4. **mastery:** 反映後 KC に `mastery_from_kc(kc, has_contact=True)`（クイズ受験は「接触あり」とみなす）。
5. **対象 run:** プロジェクトの最新 COMPLETED な `kc_analysis` run。行が無ければ新規作成
   （blame 痕跡ゼロの単独開発 / PM を救済）。最新 KC run が無い場合は反映をスキップ（アンカー不在）。
6. **集計行（`dev_id IS NULL` / `github_handle IS NULL`）:** 当該ファイルの全 dev/handle 行の
   `max` で再導出して upsert（029 の集約方針）。
7. **`quiz_results.kc_before` / `kc_after`:** 反映前後の **実 KC** に格上げ（暫定値を廃止）。
8. **decay / 半減期:** 外部仕様に式が無いため MVP では導入しない（**不明**、ADR 0003 と整合）。

## 冪等性

`max` 採用は加算ではないため再配送（at-least-once）/ 再採点で多重加算されない。再採点でスコアが
下がっても `max` により KC は下がらない（理解の認定は剥奪しない方針）。

## 対象外

- 機能（feature）単位の KC 認定 → 054 / 055。
- `certified_via="review"`（レビュー由来の認定）→ 将来。
- KC 精密式（decay / 信頼度減衰）→ 外部仕様待ち。
