# 初回解析時に機能（feature）単位のベースライン理解度クイズを生成・出題する

## 概要

git blame ベースの KC は「単独開発」や「コードを書かない PM」の理解を計測できない（→ 053 でクイズ認定の
土台を作る）。本 issue はその上で、**初回解析時に機能（feature）ごとのベースライン理解度クイズを自動生成**し、
チームメンバー（開発者 / PM）がそれを解くことで **機能単位の初期 KC = 理解負債の初期値**を計測する仕組みを作る。

既存クイズは **ファイル単位**（`quiz_sessions.file_path`）だが、本 issue では **機能単位**へ拡張する
（052 の `features` / `feature_files` を入力に、機能を代表するコードからクイズを生成）。採点結果は 053 の
`certified_via="quiz"` 経路で KC に反映される。

## 背景・目的

### 現状（クイズはファイル単位・ユーザー操作起点・ベースラインが無い）

- `quiz_generation`（`backend/service/service/pipelines/quiz_generation.py`）は `file_path` を指定して
  単一ファイルから 5 問を生成する。機能スコープは無い。
- クイズ生成は**ユーザーが受験ボタンを押す**ことで起動する（受験対象の自動選定は 029/030 由来、034 は対象外）。
  「初回解析時に全機能のベースラインを取る」流れは無い。
- 初期 KC は authorship のみ（053 前は blame 上限 0.6）。単独開発/PM では機能の理解度が空欄のまま。

### 目的

1. `quiz_sessions` を**機能スコープに対応**させる（`feature_id` / `granularity` を追加。`file_path` 単独受験も維持）。
2. 初回解析（052 のクラスタリング → 029 の KC 算出の後）に、**機能ごとのベースラインクイズ**を生成する
   オーケストレーションを追加する（受験者 × 機能でセッションを起こす）。
3. 機能を代表するコード（`feature_files` の中心ファイル群）から Gemini で設問を生成する（ファイル単一でなく機能横断）。
4. 採点結果は 053 経由で機能配下ファイルの KC に反映され、機能単位 KC（055 が集計）の初期値になる。

### 前提 issue（depends_on）

- **issue 052** `docs/issue/052-backend-measurement-granularity-and-feature-model.md` — `features` /
  `feature_files` / `Granularity` enum / クラスタリングパイプライン。本 issue の出題対象＝機能はここで作られる。
- **issue 053** `docs/issue/053-backend-quiz-certified-kc.md` — `certified_via="quiz"` の KC 反映。採点後に
  機能配下ファイルの KC を更新する経路はここが所有。本 issue は機能→ファイル展開して 053 のフックに渡す。
- **issue 034** `docs/issue/034-backend-quiz-generation-and-grading-pipelines.md` — クイズ生成・採点・API の土台。
  本 issue は `quiz_generation` を機能スコープへ拡張し、生成オーケストレーションを足す。

## データモデル（変更）

### `quiz_sessions`（`backend/shared/shared/models/quiz_session.py`）に列追加

| 追加列 | 型 | 備考 |
|---|---|---|
| `granularity` | `str`（`Granularity`、default `file`） | `feature` / `file`。後方互換のため default は `file` |
| `feature_id` | `uuid.UUID \| None` | `granularity="feature"` のとき `features.id`。`file` のとき `None` |
| `is_baseline` | `bool`（default `false`） | 初回ベースライン受験フラグ（自動生成と手動受験の区別・集計用） |

- `granularity="feature"` のセッションは `file_path` を**代表ファイル or 空**にし、対象は `feature_id` で解決する。
- 既存のファイル単位受験（`granularity="file"`）はそのまま動く（列追加は後方互換）。

## パイプライン・API

### 生成（`quiz_generation` の機能スコープ拡張）

- `QuizGenerationRequest` に `granularity` / `feature_id` を追加。`feature` のとき：
  1. `feature_files` から当該機能の代表ファイル群（`confidence` 上位 / 依存中心など）を選ぶ。
  2. `GitHubGitClient` で内容取得し、`features.description` と合わせて Gemini に渡し、**機能横断の理解度設問**を生成。
  3. `quiz_session.questions` に保存（正答/採点基準は非公開フィールド、配信時除去は 034 の既存処理）。

### 初回ベースラインの生成オーケストレーション

- 新 API `POST .../projects/{project_slug}/baseline-quizzes`（または初回解析ランの 1 ステージ）で、
  **対象メンバー × 全機能**のベースラインセッションを作成し、各機能のクイズ生成 Job を enqueue する。
  - 対象メンバー：MVP は「受験を要求する」明示操作 or プロジェクトの全 active メンバー（どちらを既定にするかは
    実装時に確認。過剰な Job 大量発行を避けるため**オプトイン / 段階生成**を既定とする）。
  - `is_baseline=true` で起票。受験 UI への導線は 056（フロント）が担う。
- 解析ランへの組み込み順序：**052 クラスタリング → 029 KC → 本ベースライン生成**。052 で保留した
  「解析ランステージへの組み込み」をここで確定する（`analysis-run-store` の stage 追加 or 既存 stage 後続トリガ）。

### 採点 → KC 反映

- `quiz_grading`（034）+ 053 の KC 反映を流用。`granularity="feature"` のセッションは、採点後に
  **機能配下ファイル群へ KC を展開**して 053 のフックに渡す（機能 KC の実体はファイル KC のロールアップ=055）。
  展開方針（全ファイル一律 / `confidence` 加重）は本 issue で確定（053 の写像と整合）。

## タスク

### shared
- [ ] `models/quiz_session.py` に `granularity` / `feature_id` / `is_baseline` を追加。
- [ ] `schemas/quiz.py` の `QuizGenerationRequest` に `granularity` / `feature_id` を追加。

### api
- [ ] Alembic マイグレーションで `quiz_sessions` に 3 列追加。
- [ ] `quizzes.py` に **ベースライン生成エンドポイント**（受験者 × 機能でセッション作成 + 生成 enqueue）を追加。
      `OrgScope` 認可・`developer_id == current_user.id`（自分の受験）または管理者が他メンバー分を起票する場合の認可を明記。
- [ ] 機能スコープのセッション取得が既存配信（`GET .../quizzes/{id}`）で破綻しないこと（`file` 組み立ての分岐）。

### service
- [ ] `pipelines/quiz_generation.py` を機能スコープ対応（`feature_files` から代表ファイル選定 + 機能横断設問生成）。
- [ ] `pipelines/quiz_grading.py`（+ 053）で機能セッションの採点結果を機能配下ファイルへ KC 展開。
- [ ] 初回ベースライン生成のオーケストレーション（解析ランへの組み込み or 専用 enqueue）。Job 大量発行の抑制（段階/オプトイン）。

### test
- [ ] api：ベースライン生成が機能数分のセッション + 生成 Job を起こすこと（`MockTaskDispatcher` 呼び出し回数）。認可。
- [ ] service：機能スコープの `quiz_generation` が `feature_files` から設問を生成すること。採点 → 機能配下ファイルへ KC 反映（053 連携）。
- [ ] 後方互換：既存ファイル単位受験（`granularity="file"`）が変わらず動くこと。

## 完了条件
- 初回解析後（052 → 029 の後）に、機能ごとのベースライン理解度クイズが自動生成・起票される。
- メンバーがベースラインクイズを解くと、機能配下ファイルの KC が 053 経由で更新され、機能の初期 KC（理解負債の初期値）が定まる。
- 単独開発 / コードを書かない PM でも、ベースラインクイズの解答で機能理解度が計測される（blame 非依存）。
- 既存のファイル単位クイズが後方互換で動作する。
- バックエンド：`uv run ruff check/format --check`・`uv run ty check`・`pytest`（shared/api/service）が通る。
- `CHANGELOG.md`（日本語）に `Added`（機能単位クイズ + 初回ベースライン生成）/ `Changed`（quiz_sessions 列追加）を追記。

## 対象外・保留
- **機能単位 KC/負債の集計・配信 API** → 055。
- **受験 UI / ベースライン導線のフロント** → 056。
- **クラス/関数単位のクイズ** → 057。
- **対象メンバー自動選定の高度化**（役割別の出題設計など）→ 将来。

## 参考
- 既存実装：`backend/service/service/pipelines/quiz_generation.py` / `quiz_grading.py`、
  `backend/shared/shared/models/quiz_session.py`、`backend/api/app/api/v1/quizzes.py`、
  `backend/shared/shared/schemas/quiz.py`。
- 関連 issue：[052 機能モデル](./052-backend-measurement-granularity-and-feature-model.md)、
  [053 クイズ KC 認定](./053-backend-quiz-certified-kc.md)、
  [034 クイズ生成・採点](./034-backend-quiz-generation-and-grading-pipelines.md)、
  [010 クイズ返済体験](./010-quiz-repayment-experience.md)。
- 規約：`CLAUDE.md` / `backend/CLAUDE.md`（方式 B・snake_case・冪等性・CHANGELOG 日本語・ゲート）。
