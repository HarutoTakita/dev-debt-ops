# ADR 0001: 解析データモデルと同一性の正規化方針

- ステータス: 採択（issue 026）
- 日付: 2026-06-19
- 文脈 issue: `docs/issue/026-backend-analysis-data-model-and-shared-tables.md`

## 背景

Overview / Matrix / Galaxy / Quizzes / Agents / Learning の各機能は「あるリポジトリのある時点を解析した結果」を
土台に描画される。独立した製品仕様書が存在しないため、後続の解析 issue（027〜037）が `file_path` / `run` /
`dev_id` を二重定義して join 不能になることを防ぐ目的で、共有 2 テーブルの軸と識別子の正規形を**決定**として明示する。

## 決定

### 1. File 同一性

- File はまず `(run_id, path)` で同定する（`repo_file` の一意制約 `uq_repo_files_run_id_path`）。
- run / repo 横断の「同じファイル」は `repo_file.path`（リポジトリルートからの相対パス）の一致で**近似**する。
- git rename 追跡は本 issue の範囲外。必要になった場合は 027（GitHub 履歴クライアント拡張）の blame/履歴で扱う。
- したがって `repo_file.path` を File 同一性の唯一の安定キーとする。後続の `file_debt` / `file_kc` / `dependency`
  は `repo_file`（または `(run_id, path)`）を File アンカーとして参照する。

### 2. 開発者識別子（dev_id）

- 解析（authorship / blame）は GitHub author（login / email）単位で発生する。一方 Rosetta のユーザは `users.id`。
- 後続テーブル（`file_kc.dev_id`、`assigned_developers` 等。029 / 030）は **`users.id` を主**とし、GitHub login は
  マッピング経由で突合する。突合経路は `api/app/api/v1/github.py` の `resolve_installation_id`（user → github_login 解決）を参照する。
- GitHub author が Rosetta ユーザに紐づかない場合（外部コミッタ等）の扱いは、各ドメイン issue が
  「GitHub login を保持しつつ `users.id` は null 可」とするか判断する（本 ADR では `users.id` 主・login 従の原則のみ確定）。

### 3. run スコープ

- 解析データは project 単位（1 project = 1 repo）。`analysis_run.project_id`（FK → `projects.id`）を全解析データの親スコープとする。
- trend（週次推移 = 地層グラフ）は同 project の `analysis_run` を `commit_sha` + `created_at` の時系列で並べて導出する。
- 037（定期スキャン）は同一 `commit_sha` の重複 run を抑止する（冪等な巡回 enqueue のキーに `commit_sha` を使う）。

### 4. JobType 命名規約

- `JobType`（`shared/shared/enums.py`）の値は **lowercase snake_case**。queue / task path 名へは `_` → `-` 変換で対応する
  （例: `code_debt_detection` → `code-debt-detection`）。後続の解析 issue は 1 値ずつ同形で追加する。
- `analysis_run.kind` はこの `JobType` 値に、`analysis_run.status` は `JobStatus` 値（UPPERCASE）に揃える。
  いずれも String 保存（native PG enum を作らない）とし、新 `kind` 追加でマイグレーションが不要になるようにする。

### 5. pgvector

- マイグレーション（0006）で `CREATE EXTENSION IF NOT EXISTS vector` により拡張を**有効化のみ**行う。
- `vector` 型の列・`pgvector` Python 依存・埋め込み類似検索（重複検知・概念マッピング）の本実装は将来 issue に委ねる。

## 影響

- 027〜037 の各解析/配信 issue は本 ADR の同一性・スコープ・命名規約に従って `repo_file` / `analysis_run` を親に新テーブルを設計する。
- `shared` の依存は `pydantic` + `sqlmodel` のみを維持する（重い依存は service 側）。Alembic は api 所有。
