# 多粒度計測を拡張する（フォルダ/クラス/関数 + コード負債への横展開）【トラッキング】

## 概要
052〜056 で「**機能（feature）単位の理解負債**」を MVP として実装する。本 issue はその先の全体像
＝「コード負債・理解負債を **フォルダ / ファイル / クラス / 関数**の各粒度で計測・表示する」拡張を
**トラッキング**する親 issue。MVP 完了後に、ここから個別 issue を切り出す。

## 背景・目的
- ユーザーの最終目標は「機能 / フォルダ / ファイル / クラス / 関数」と粒度を自在に切り替え、**コード負債も
  理解負債も**同じ軸で計測・表示できること。
- MVP（052〜056）は「機能単位 × 理解負債」に絞った縦切り。残る軸（他粒度 × コード負債）を本 issue で俯瞰し、
  スコープ膨張を防ぎつつ抜け漏れを記録する。

> **優先度（issue 058 リポジション後）:** コード負債は「主役」ではなく**ホットスポット（hotspot）= 理解負債を
> 優先順位づけするリスク信号**へ格下げされた。したがって本トラッキング（特に B: 全粒度のコード負債展開）の
> **優先度は低い**。理解負債（クイズ実測 KC・機能単位）の磨き込みを優先し、子 issue 060/061/062 は後回しでよい。

## 残タスク（MVP 後に個別 issue 化）

### A. コード負債の粒度集計
- [ ] コード負債（複雑度 / 重複 / デッド）の **機能単位ロールアップ**（055 で KC は集計済み、code は max 流用だった部分を本実装）。
- [ ] フォルダ単位のコード負債集計（`module` 射影の本実装）。
- [ ] Overview/マトリクスで粒度別にコード負債軸を表示（056 のコード負債側）。

### B. クラス / 関数粒度（AST 解析）
- [ ] ソースを AST 解析してクラス / 関数の範囲を抽出（言語別パーサ。既存の正規表現ベース複雑度推定 `code_analysis.py` を超える解析層）。
- [ ] クラス / 関数単位の KC（blame 行範囲 → シンボル範囲へのマッピング）とコード負債（シンボル単位の複雑度/重複）。
- [ ] `Granularity.CLASS` / `FUNCTION`（052 で値は定義済み）の実計測・配信・表示を有効化（056 の disabled を解除）。

### C. 横断
- [ ] 粒度間の整合（関数 → クラス → ファイル → フォルダ/機能 のロールアップ一貫性）。
- [ ] クイズ/学習の粒度対応（クラス/関数単位の設問は過剰になり得るため、適切な粒度の検討）。
- [ ] 定期再計測（粒度別スナップショットのトレンド）。

## 進捗

- **2026-06-22:** MVP（052–056）完了。本トラッキングから子 issue を切り出し:
  - [060 コード負債の粒度集計の本実装](./060-backend-code-debt-granularity-aggregation.md)（A の集計深化）
  - [061 クラス/関数粒度の AST 計測](./061-backend-class-function-granularity-ast.md)（B）
  - [062 粒度間整合・定期再計測・クイズ粒度](./062-cross-granularity-consistency-and-periodic.md)（C）
- スライスとして「056 のコード負債側表示」を先行実装: 機能/フォルダビュー（`feature-debt-list`）に
  コード負債軸（`code_debt_score`）を表示し、機能ノードのコード負債ロールアップ（配下ファイルの max）を
  テストで担保。残りの集計深化は 060、AST は 061、横断は 062。本トラッキングは 060/061/062 完了まで **open** のまま。

## 完了条件（本トラッキングの解消条件）
- コード負債・理解負債の双方が、機能 / フォルダ / ファイル / クラス / 関数の各粒度で計測・表示できる。
- 上記 A/B/C（子 issue 060/061/062）が実装・マージされている。

## 依存・順序
- 前提：[052](./052-backend-measurement-granularity-and-feature-model.md) /
  [053](./053-backend-quiz-certified-kc.md) / [054](./054-backend-initial-feature-baseline-quiz.md) /
  [055](./055-backend-feature-granularity-debt-aggregation-api.md) /
  [056](./056-frontend-granularity-switch-and-feature-debt-view.md)（MVP）。
- 既存基盤：`backend/service/service/services/code_analysis.py`（複雑度/重複/デッドの検知）、
  `backend/service/service/pipelines/kc_analysis.py`（KC 算出）、`backend/api/app/services/debt_query.py`（集計/配信）。

## 参考
- 関連 issue：028（コード負債検知）/ 029（KC）/ 030（知識負債検知）/ 031（Overview API）/ 032（Galaxy API）。
- 想定ラベル：`feature`, `backend`, `frontend`。
