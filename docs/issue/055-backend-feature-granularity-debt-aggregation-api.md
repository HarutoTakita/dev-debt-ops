# 機能（feature）単位の理解負債を集計し、粒度パラメータ付き API で配信する

## 概要

052 で機能↔ファイルの写像（`features` / `feature_files`）が、053/054 で機能のクイズ KC が入る。本 issue は
ファイル単位の KC を **機能（feature）単位へロールアップ**し、Overview / Galaxy / 負債レジストリの各 API に
**`granularity` パラメータ**（MVP は `feature` / `folder` / `file`）を足して、機能単位の理解負債を配信する。

> 本 issue は **理解負債（KC）の機能単位集計・配信**に絞る（ユーザーの「まずは機能単位のみ、理解負債の計測」を満たす）。
> コード負債の機能単位集計と、フォルダ/クラス/関数の他粒度は **057** へ送る（API の `granularity` 値だけ先行で確保する）。

## 背景・目的

### 現状（配信はファイル単位固定）

- `build_overview`（`backend/api/app/services/debt_query.py`）は `file_kc`（KC(file) 集計行）と `code_debts` を
  ファイル単位で結合し、`FileDebtOut`（path / code_debt_score / knowledge_coverage / priority）の散布図を返す。
  集計の最粗単位は無く、フロントは常に全ファイルを受け取る。
- Galaxy（`backend/api/app/services/galaxy_query.py`）は `module = ディレクトリ`で「星系」集計するが、これは
  052 の「機能」ではない（フォルダ粒度に相当）。
- `priority` は `derive_priority(code, knowledge_coverage)`（`debt_query.py`）で 2 軸（コード負債 × 理解ギャップ）から
  P0–P3 を導出。機能単位でも同じ語彙で出したい。

### 目的

1. KC(file) を `feature_files` で機能へロールアップする集計関数を追加（集約方針は 029/048 と整合：MVP は平均 or max を本 issue で確定）。
2. Overview / Galaxy / 負債レジストリ API に `granularity` クエリパラメータを追加（`feature` / `folder` / `file`）。
3. `granularity=feature` のとき、機能を 1 点（または 1 ノード）として KC・理解負債・優先度を返す。
4. 機能配下のドリルダウン（機能 → ファイル）に対応する（フロント 056 のツリー/展開に供給）。

### 前提 issue（depends_on）

- **issue 052** — `features` / `feature_files` / `Granularity`。集計の写像元。
- **issue 053 / 054** — 機能のクイズ KC。機能 KC の実体（authorship + quiz の KC をファイル経由で集計）。
- **issue 031 / 032** — Overview / 負債レジストリ / Galaxy 配信 API の所有者。本 issue はそれらに `granularity` を増設する
  （`docs/issue/031-backend-overview-and-debt-registry-api.md` / `docs/issue/032-backend-galaxy-personal-kc-api.md`）。

## 集計の設計（本 issue で確定）

### 機能 KC のロールアップ

```
KC(feature) = aggregate( KC(file) for file in feature_files[feature] )
```

- `aggregate` は MVP で **平均**（多数の理解済みファイルに 1 つの暗部があっても薄まりすぎない閾値運用を 056 と調整）か
  **min（最弱リンク）**のどちらかを本 issue で確定。`confidence` 加重平均も選択肢。
  → 「理解負債 = 弱いところを可視化」目的に沿うなら **min 寄り**を推奨し、表示は平均と min を両方返すことも検討。
- 機能の `code_debt_score`（057 でコード負債を機能集計するまでは）は **暫定で配下 `code_debts` の max**（既存の
  ファイル集計と同じく `max`）を流用してよい。本 issue の主眼は KC（理解負債）側。
- `priority` は機能の `(code, knowledge_coverage)` に `derive_priority` を適用（既存ロジック再利用）。

### `folder` 粒度

既存 `module`（ディレクトリ）を `folder` 粒度として射影（新規計算は最小限）。`feature` と `folder` が**別物**で
あることを API/フロントで明示する。

## API（`granularity` 増設）

`debt_query` / `galaxy_query` を消費する既存ルート（031/032）に `?granularity=feature|folder|file`（default `file`）を追加。

- Overview：`granularity=feature` で `FeatureDebtOut`（`feature_key` / `name` / `code_debt_score` /
  `knowledge_coverage` / `priority` / `file_count` / `weakest_file?`）の配列を返す。`file` は従来の `FileDebtOut`。
- ドリルダウン：`GET .../features/{feature_key}`（機能配下ファイルの `FileDebtOut` 一覧）を追加（056 の展開用）。
- Galaxy：`granularity=feature` のとき「星系 = 機能」で集計（従来のディレクトリ星系は `folder`）。
- レスポンスは **snake_case 維持**（既存契約と整合）。フロント Zod スキーマ（`frontend/src/lib/api/schemas.ts`）に
  `featureDebtSchema` 等を追加（056 が消費）。

## タスク

### shared
- [ ] 配信スキーマ（必要なら `shared` 側）に `FeatureDebtOut` 等を追加（または api スキーマに閉じる）。

### api（`backend/api/app/`）
- [ ] `services/debt_query.py` に `build_overview(granularity=...)` の分岐と機能ロールアップ集計を追加。
- [ ] `services/galaxy_query.py` に `granularity=feature` の星系集計を追加（`module` は `folder` に射影）。
- [ ] Overview / 負債レジストリ / Galaxy のルート（031/032）に `granularity` クエリパラメータを追加。
      機能ドリルダウン `GET .../features/{feature_key}` を追加。**Annotated DI param 順序を変更しない**。
- [ ] 集約方針（平均/min/confidence 加重）を本 issue / 実装コメントに明記。

### test
- [ ] api：`granularity=feature` の Overview が機能数分の点を返し、KC が配下ファイルの集約と一致すること。
- [ ] api：`granularity=folder` が `module` 射影と一致、`granularity=file` が従来挙動と完全後方互換であること。
- [ ] api：機能ドリルダウンが配下ファイル一覧を返すこと。`priority` が `derive_priority` と整合すること。

## 完了条件
- Overview / Galaxy / 負債レジストリ API が `granularity=feature|folder|file` を受け、機能単位の理解負債を配信できる。
- 機能 KC が配下ファイル KC（authorship + quiz）のロールアップとして算出され、集約方針が本 issue / 実装に明記される。
- 機能ドリルダウン（機能 → ファイル）が動作する。
- `granularity` 未指定時は従来のファイル単位挙動と完全後方互換。
- バックエンド：`uv run ruff check/format --check`・`uv run ty check`・`pytest`（shared/api/service）が通る。
- `CHANGELOG.md`（日本語）に `Added`（機能単位集計 + `granularity` パラメータ + 機能ドリルダウン）を追記。

## 対象外・保留
- **コード負債の機能単位集計の本実装**（複雑度/重複/デッドの機能ロールアップ）→ 057（本 issue は KC 主眼、code は max 流用）。
- **フォルダ/クラス/関数の実計測**（class/function）→ 057（API 値だけ確保）。
- **フロントの粒度切替 UI / 表示** → 056。

## 参考
- 既存実装：`backend/api/app/services/debt_query.py`（`build_overview` / `derive_priority`）、
  `backend/api/app/services/galaxy_query.py`（星系集計）、`backend/api/app/schemas/overview.py`（`FileDebtOut` / `OverviewOut`）、
  `backend/shared/shared/models/file_kc.py`、052 の `feature_files`。
- 関連 issue：[052 機能モデル](./052-backend-measurement-granularity-and-feature-model.md)、
  [053 クイズ KC 認定](./053-backend-quiz-certified-kc.md)、[054 機能ベースラインクイズ](./054-backend-initial-feature-baseline-quiz.md)、
  [031 Overview/負債レジストリ API](./031-backend-overview-and-debt-registry-api.md)、
  [032 Galaxy/個人 KC API](./032-backend-galaxy-personal-kc-api.md)、[057 多粒度・コード負債拡張](./057-multi-granularity-code-debt-rollout.md)。
- 規約：`CLAUDE.md` / `backend/CLAUDE.md`（snake_case 配信・Annotated DI 順序・CHANGELOG 日本語・ゲート）。
