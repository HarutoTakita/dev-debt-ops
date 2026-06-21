# クイズ採点結果を KC へ反映する（`certified_via="quiz"`／blame 非依存の理解度認定）

## 概要

現状 KC（Knowledge Coverage）は **git blame の authorship からのみ**算出され、`certified_via="authorship"` として
**上限 0.6**（`_AUTHORSHIP_KC_CEILING`、`backend/service/service/pipelines/kc_analysis.py`）でキャップされる。
これは「コードに触った量 ≠ 理解」という妥当な前提だが、結果として **(1) 単独開発（全行を 1 人が書いた）** や
**(2) コードを書かない PM/レビュアの理解** を KC に反映できない（blame 痕跡が無い／偏るため star に到達しない）。

クイズ基盤（`quiz_generation` / `quiz_grading` パイプライン、`quiz_sessions`/`quiz_answers`/`quiz_results`）は実在
するが、**採点結果を `file_kc` へ反映するフックが未実装**で、`backend/service/service/pipelines/quiz_grading.py`
には「KC 反映フック（issue 029 所有）: `certified_via="quiz"` の file_kc 更新はここで呼ぶ配線位置」という
**コメントだけ**が残る（実体なし）。

本 issue はこの**フックを実装**し、クイズ合格による KC を **blame 非依存・上限なし（star 到達可能）**で
`file_kc` に書き込む。これにより「コードを書いていなくてもクイズに答えれば理解度として計測される」状態を作る。

## 背景・目的

### 現状（クイズは採点されるが KC に反映されない）

- `quiz_grading.process` は Gemini で意味採点し `quiz_results`（`understood` / `gap_concepts` / `kc_before` /
  `kc_after`）を書くが、`file_kc` は**一切更新しない**。`kc_before`/`kc_after` は**暫定値**にとどまる
  （034 が「本算出は 029」と委譲、`docs/issue/034-backend-quiz-generation-and-grading-pipelines.md`）。
- `file_kc`（`backend/shared/shared/models/file_kc.py`）には `certified_via: str | None  # quiz / authorship / review`
  列が**既にある**が、現状 `"quiz"` を書く経路は無い（authorship のみ実装、`kc_analysis.py`）。
- KC→mastery 閾値は `mastery_from_kc`（`kc_analysis.py`）：`star ≥0.7 / dim_star ≥0.4 / black_hole <0.4（接触あり）
  / unexplored（接触なし）`。authorship は 0.6 上限のため**単独で star にならない**設計（issue 048）。

### 目的

1. `quiz_grading` の採点完了時に、対象（受験者 × ファイル）の KC を **`certified_via="quiz"` で `file_kc` に upsert**する。
2. クイズ認定 KC は **authorship の 0.6 上限を適用しない**（合格すれば star=≥0.7 到達可）。これが blame 非依存の核。
3. KC(file) 集計行（`dev_id IS NULL`）を、クイズ認定後に再導出して整合させる（集計方針は 029 ADR に従う）。
4. `kc_before`/`kc_after` を「**反映前後の実 KC**」に格上げし、暫定値ではなく `file_kc` の値と一致させる。

### 前提 issue（depends_on）

- **issue 029** `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md` — `file_kc` と KC 算出の所有者。
  029 が「`certified_via="quiz"` の取り込みは 034（採点）が `file_kc` を更新する前提で**後続フックのみ用意**」と明記。
  本 issue がそのフックの**実装**。upsert 競合キー `(run_id, file_path, dev_id)` と mastery 閾値は 029 の規約に従う。
- **issue 034** `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — `quiz_grading` パイプライン本体。
  本 issue は `quiz_grading.process` の末尾（採点後）に KC 反映処理を**追加**する。

### 独自性（他 issue との差分）

029 は authorship 由来の KC を所有し、034 は採点（`quiz_results`）を所有する。本 issue は **「採点スコア → KC への
変換と `file_kc` 書き込み」という両者の橋渡し**を唯一所有する。KC 反映式（スコア→KC の写像）を製品判断として
確定し、ADR 化する（捏造した精密式は導入しない）。

## KC 反映の設計（本 issue で確定・ADR 化）

### どの run の `file_kc` を更新するか

クイズは受験時点の最新 KC run に紐づく。`quiz_sessions.source_kc`（受験対象選定時の KC スナップショット）と
受験者・ファイルから、対象 `file_kc` 行 `(run_id, file_path, dev_id=受験者)` を特定する。該当 run の `file_kc` を
**upsert で書き換える**（行が無ければ新規＝blame 痕跡ゼロの単独開発/PM ケースを救済）。

### スコア → KC 写像（MVP・ADR 化）

```
kc_quiz = quiz_score        # 採点スコア（0..1）をそのまま認定 KC とする MVP 式
```

- authorship 行と**別系列**として `certified_via="quiz"` の行を持つ（または同一行を quiz 認定で上書きし、より高い方を採る）。
  **MVP は「同一 (run, file, dev) について authorship と quiz の高い方を採用」**（`max(kc_auth_capped, kc_quiz)`）。
  これにより「書いた人＝authorship」も「書いてない理解者＝quiz」も同じ軸で star に到達できる。
- `mastery` は反映後 KC に `mastery_from_kc(kc, has_contact=True)` を再適用（クイズ受験は「接触あり」とみなす）。
- decay / 半減期は外部仕様に式が無いため MVP では入れない（029 と整合、ADR に「不明」を明記）。

### KC(file) 集計行の再導出

`dev_id IS NULL` の集計行は、当該ファイルの全 dev 行（authorship + quiz）から 029 の集約方針（max or 平均）で
再計算して upsert する。

## タスク

### shared（`backend/shared/shared/`）
- [ ] 反映式・閾値を確定する ADR を `docs/adr/` に追記（029 の KC ADR と相互参照。「quiz は上限なし」「max 採用」「decay なし=不明」）。
      （モデル変更は基本不要。必要なら `quiz_results` に反映済みフラグ列を追加し冪等化。）

### service（`backend/service/service/`）
- [ ] `pipelines/quiz_grading.py` の採点完了後に **KC 反映処理を実装**（現コメント「KC 反映フック」位置）。
      `_upsert_file_kc(..., certified_via="quiz")` 相当を呼び、authorship の 0.6 キャップを適用しない。
- [ ] 対象 `file_kc` 行の特定（受験者 × ファイル × 最新 KC run）。行が無ければ新規作成（単独開発/PM 救済）。
- [ ] KC(file) 集計行（`dev_id IS NULL`）を再導出して upsert（029 の集約方針）。
- [ ] `quiz_results.kc_before` / `kc_after` を**反映前後の実 KC**に揃える（暫定値からの格上げ）。
- [ ] 冪等性：再配送（at-least-once）や再採点で KC が多重加算されないこと（`max` 採用＝加算でないので自然に冪等。
      再採点でスコアが下がっても KC を下げない方針なら明記）。

### test
- [ ] service：`quiz_grading.process` が採点後に `file_kc` を `certified_via="quiz"` で upsert すること。
      合格（高スコア）で KC が 0.6 を超え `mastery="star"` になること（authorship では到達不可なことと対比）。
- [ ] service：blame 痕跡ゼロのファイル（`file_kc` 行が無い）でクイズ合格 → 新規 `file_kc` 行が立つこと（単独開発/PM 救済）。
- [ ] service：再配送/再採点で KC が多重加算されない冪等性。KC(file) 集計行が dev 行から正しく再導出されること。
- [ ] api（既存流用）：`GET .../quizzes/{id}/result` の `kc_before`/`kc_after` が `file_kc` の実値と整合すること。

## 完了条件
- クイズ採点完了時に `file_kc` の対象行が `certified_via="quiz"` で upsert され、blame 上限 0.6 を超えて star に到達できる。
- blame 痕跡が無い（単独開発で 1 人 / コードを書かない PM）ファイルでも、クイズ合格で KC が計測・記録される。
- `quiz_results.kc_before` / `kc_after` が `file_kc` の実 KC と一致し、暫定値ではなくなる。
- 反映式・上限・集約方針・decay 不明が `docs/adr/` の ADR に記録される。
- 再配送/再採点で KC が多重加算されない（冪等）。
- バックエンド：`uv run ruff check/format --check`・`uv run ty check`・`pytest`（shared/api/service）が通る。
- `CHANGELOG.md`（日本語）に `Added`（クイズ採点による KC 認定 `certified_via="quiz"`）/ `Changed`（kc_before/after を実値化）を追記。

## 対象外・保留
- **機能（feature）単位での KC 認定** → 054（機能ベースラインクイズ）/ 055（機能ロールアップ）。本 issue は**ファイル単位**の認定。
- **クイズ対象の自動選定**（低 KC ファイル抽出）→ 029/030 由来。本 issue は採点済みセッションの反映のみ。
- **review 由来の KC 認定**（`certified_via="review"`）→ 将来。
- **KC 精密式（decay / 半減期）** → 外部仕様に式が無く MVP 暫定（ADR に「不明」を残す）。

## 参考
- 既存実装：`backend/service/service/pipelines/quiz_grading.py`（KC 反映フックのコメント位置）、
  `backend/service/service/pipelines/kc_analysis.py`（`_upsert_file_kc` / `_AUTHORSHIP_KC_CEILING` /
  `mastery_from_kc` / 集計行の作り方）、`backend/shared/shared/models/file_kc.py`（`certified_via` 列）、
  `backend/shared/shared/models/quiz_result.py`（`kc_before`/`kc_after`）。
- 関連 issue：[029 KC パイプライン](./029-backend-kc-knowledge-coverage-pipeline.md)、
  [034 クイズ生成・採点](./034-backend-quiz-generation-and-grading-pipelines.md)、
  [048 Galaxy KC mastered 修正](./048-galaxy-kc-all-mastered-fix.md)（0.6 上限の背景）、
  [054 初回機能ベースラインクイズ](./054-backend-initial-feature-baseline-quiz.md)。
- 規約：`CLAUDE.md` / `backend/CLAUDE.md`（snake_case 配信・冪等性・CHANGELOG 日本語・ゲート）。
