# ADR 0003: KC（Knowledge Coverage）算出式・mastery 閾値・集約方針

- ステータス: 採択（issue 029）
- 日付: 2026-06-20
- 文脈 issue: `docs/issue/029-backend-kc-knowledge-coverage-pipeline.md`
- 関連: [[ADR 0001]]（File 同一性・dev 識別子の正規化）、[[ADR 0002]]（git 履歴取得・authorship 突合）

## 背景

Galaxy / Overview / Matrix の「チーム理解度」軸は KC ∈ [0,1] を入力に描画されるが、KC を算出・永続化する
裏側が無くフロントの mock 直読みで成立していた。KC の**厳密な算出式（半減期・decay 等）は独立した外部
仕様書がリポジトリに存在しない**（doc 009 は §5.1 を参照のみで本文の式が無い）。捏造した精密式を入れず、
MVP の暫定式・閾値・集約方針を**製品判断として明示**し、後続（032 配信 / 034 quiz 加算）が一貫して使える形にする。

## 決定

### 1. KC(file,dev) — blame 行シェア（MVP）

- KC(file,dev) = **当該 dev が最終変更した行の割合**（027 の `get_blame` の行レンジを著者ごとに合算し、
  ファイル総行数で割る）。値域 [0,1]。`certified_via = "authorship"` として記録する。
- **半減期 / 時間減衰（decay）は不明**のため MVP では入れない（将来、commit 日時で重み付けする余地を残す）。
- `certified_via = "review"`（著者でなく PR レビューのみ）の加点は、027 の PR レビューメタが取れる場合に
  **authorship より低い重み（暫定 0.3 倍）**で加える方針とする。本 issue の MVP 実装は authorship のみを
  確実に算出し、review 重みは ADR 上の確定値として記す（実取り込みは PR レビュー突合が安定してから）。

### 2. KC(file) 集約（`dev_id IS NULL` 行）

- KC(file) = 当該ファイルの dev 行 KC の **最大値**（「少なくとも 1 人がよく理解していれば、そのファイルの
  知識被覆は高い」とみなす MVP）。dev 行が無い（blame 痕跡なし）ファイルは KC(file) = 0.0。
- 032 は星系（module）集計で `starSystemSchema.kc` = 「KC(file) の平均」を使う（`schemas.ts`）。本 ADR は
  **KC(file) 単体の集約 = max**、**星系集計 = KC(file) の平均**（032 所有）と役割を分ける。

### 3. KC → mastery 閾値（doc 009 §の表を正典）

| `kc` | `mastery` | 意味 |
|---|---|---|
| `>= 0.7` | `star` | マスター済み |
| `0.4 <= kc < 0.7` | `dim_star` | 部分理解 |
| `< 0.4` かつ **接触あり**（blame 痕跡あり） | `black_hole` | 触ったが未理解 |
| **接触なし**（blame 痕跡なし） | `unexplored` | 未接触 |

- 低 KC フラグ = `kc < 0.4`（doc 007 / 009 と整合）。`black_hole` と `unexplored` の境界は「接触の有無」。
- dev 行は定義上「接触あり」。集計行は当該ファイルに blame 痕跡を持つ dev が 1 人以上いれば「接触あり」。

### 4. dev 識別子

- [[ADR 0001]] に従い `users.id` を主とする。027 の authorship 突合（`account_id` 主・`account_email` 従）で
  解決し、突合不能（外部コミッタ）は `dev_id = NULL` とし `github_handle` を保持する（**捏造しない**）。

### 5. quiz 認定フック（034 へ委譲）

- `certified_via = "quiz"` による KC 加算は本 issue では実装しない。`file_kc.certified_via` 列と upsert 経路を
  034（quiz 採点）が後から書き換えられる形にするのみ。

### 6. 永続・冪等

- `file_kc` は dev 行 `(run_id, file_path, dev_id)` UniqueConstraint と、集計行 `(run_id, file_path) WHERE
  dev_id IS NULL` の部分ユニーク索引で一意化（Postgres は NULL を区別するため集計行は部分索引が必要）。
- `dependencies` は `(run_id, from_path, to_path)` で一意化。run を `job_id` で再利用し、at-least-once
  再配送でも `on_conflict` で二重化しない。

## 影響・未確定（不明と明記）

- **不明**: KC の半減期 / decay、authorship と review の正確な重み比（暫定 0.3 を採用）、quiz 加算の係数（034）。
  これらは外部仕様書が無く、安定したデータが揃った段階で本 ADR を追補する。
- 032 は本 ADR の `file_kc` / `dependencies` を集計・配信するだけで、KC の算出・閾値判定は行わない。
