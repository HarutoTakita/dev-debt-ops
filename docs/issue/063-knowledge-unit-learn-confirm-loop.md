# 学習と確認クイズを機能（feature）単位の「単元」に統合する（Udemy 型 learn→confirm ループ）

## 概要

現状、学習（`/learning` の学習タブ）とクイズ（クイズタブ）は **1 画面のタブで並置**されているだけで、両者は
`gap_concepts` でゆるく繋がるに過ぎない。本 issue は Udemy の「レッスン＋小テスト」のように、**機能（feature）
単位の『単元』**に「**学習（input）→ 確認クイズ（output＝実測）→ KC 更新（返済の可視化）**」を対応付ける。
これにより、どの単元の理解負債を解消したかが単元ごとに見え、計測（`certified_via="quiz"` の KC 反映）も
単元と一対一になる。

> 製品判断（オーナー確定）: **単元の粒度＝機能（feature）**、**独立クイズメニューは学習へ内包して廃止**。

## 背景・目的

### 現状
- `/learning` ハブはタブ統合済み（クイズ＝実測 / 学習＝返済）だが、両者は別アーティファクト。
  - 学習: `learning_plans`（`gap_concepts`）/ `learning_steps`（order, completed, resource_id）/ `learning_resources`。
  - クイズ: `quiz_sessions`（054 で `granularity=feature` / `feature_id` / `is_baseline` 対応）→ 採点 → `quiz_results` →
    KC 反映（053 `certified_via="quiz"`、054 で機能配下ファイルへ展開）。
- 機能↔ファイル写像（052 `features`/`feature_files`）と機能 KC ロールアップ（055）は既にある。

### 目的
1. 「単元＝機能」として、機能ごとに **学習一式（input）＋ 確認クイズ（output）＋ 状態 ＋ KC** を 1 つにまとめて提示する。
2. 学習を読了 → 確認クイズに合格 → 機能 KC が上がる、という**返済の可視化**を単元単位で実現する。
3. 独立クイズメニューを廃止し、クイズは常に単元（機能）の「理解度を確認する」導線として現れる。

### 単元の状態機械（MVP）
```
未学習(unstarted) → 学習中(in_progress: 資料を開いた/読了トグル) → 確認待ち(ready_to_verify: 学習完了)
→ 理解済み(verified: 確認クイズ合格で KC≥star) ／ 要復習(needs_review: 不合格 or 低 KC)
```
- 「理解済み」判定は機能 KC（055 ロールアップ）と確認クイズ結果（053/054）から導く（閾値は ADR 0003/0006 準拠、star≥0.7）。

## データモデル（変更）

### `learning_plans` に機能スコープを追加
| 追加列 | 型 | 備考 |
|---|---|---|
| `feature_id` | `uuid.UUID \| None`（index） | プランを機能単元に紐付ける。既存の概念ベースプランは `None`（後方互換） |

- Alembic マイグレーション（chain 末尾の次番）。`developer_id`（040）と同様 index-only・FK 無し。

> 学習リソースを機能へ紐付ける写像は、当面 `learning_plans.feature_id`（プラン＝機能の単元）で表現する。
> 将来、リソース個別の機能タグ付けが要るなら別 issue。

## API（配信・生成）

### 単元一覧の配信（新規）
- `GET /orgs/{slug}/projects/{project_slug}/knowledge-units` → 単元（機能）配列。各要素:
  `feature_key` / `name` / `knowledge_coverage`（055 ロールアップ）/ `status`（上記状態機械）/
  `learning_plan_id?`（機能スコープの最新プラン）/ `quiz_session_id?`（機能の確認クイズ最新セッション + その status/score）/
  `file_count`。055 の機能ロールアップ + 053/054 の quiz_session/quiz_results + `learning_plans.feature_id` を join して算出。
- `OrgScope` 認可・snake_case 配信。

### 学習プラン生成を機能スコープ対応（035 拡張）
- `POST .../learning/plans` に `feature_id`（任意）を受け付け、`learning_plans.feature_id` をセット。
  `gap_concepts` は当該機能の低 KC ファイル/概念から導出（054 の機能展開と整合）。

### 確認クイズは 054 を流用
- 単元の「理解度を確認する」= `granularity="feature"` の `quiz_generation`（054）。採点 → 053/054 で機能配下
  ファイルへ KC 反映 → 機能 KC（055）上昇。**新規パイプラインは追加しない**。

## フロント（`/learning` を単元ハブへ再構成）

- タブ（クイズ / 学習）を廃し、**単元（機能）リスト**に。各単元カードは展開で:
  - **学習**: 機能スコープの学習プラン（`learning_steps`/`ResourceList`、未生成なら「学習プランを作る」）。
  - **確認クイズ**: 「理解度を確認する」→ 確認クイズ生成/受験（`/quizzes/{sessionId}` の受験ページは維持）。
  - **状態 / KC**: 状態バッジ（未学習〜理解済み）＋ 機能 KC%。合格後は KC↑と「理解済み」を表示（返済の可視化）。
- 独立クイズ一覧メニューは廃止（055/056 の粒度切替＝機能と整合。`nav` は「学習」1 本のまま、内容を単元ハブに）。
- i18n（ja/en）に単元状態・導線文言を追加。空状態（機能未クラスタリング/学習未生成）と 049 オートリフレッシュを配線。

## タスク

### shared / api
- [ ] `learning_plans.feature_id` 追加（Alembic）。`schemas.ts` 影響なし（配信は新エンドポイント）。
- [ ] `GET .../knowledge-units` 配信エンドポイント（機能 KC + 学習プラン + 確認クイズ状態の join）。
- [ ] `POST .../learning/plans` に `feature_id` を受け付け（035 拡張、機能スコープのプラン）。

### frontend
- [ ] `/learning` を単元（機能）ハブへ再構成（学習＋確認クイズ＋状態＋KC を単元カードに）。タブ撤去。
- [ ] `client.ts` に `getKnowledgeUnits` / `generatePlan(featureId)` 追加、Zod スキーマ追加。
- [ ] i18n・空状態・オートリフレッシュ（052 クラスタリング / 053・054 クイズ / 035 プラン完了）。

### test
- [ ] api: `knowledge-units` が機能ごとに KC/プラン/クイズ状態を返す。`learning/plans` が `feature_id` を保存。
- [ ] frontend: 単元カードの状態遷移（未学習→確認待ち→理解済み）と「理解度を確認する」導線。

## 完了条件
- `/learning` が機能単位の単元リストになり、各単元で「学習 → 確認クイズ → KC 更新（理解済み）」が回せる。
- 確認クイズ合格で機能 KC が上がり、単元の状態が「理解済み」になる（返済が単元ごとに可視化）。
- 独立クイズメニューは廃止され、クイズは単元内の確認導線としてのみ現れる（受験ページ `/quizzes/{sessionId}` は維持）。
- フロント/バックエンドのゲートが通る。`CHANGELOG.md`（日本語）に追記。

## 対象外・保留
- リソース個別の機能タグ付け（`learning_resources` → feature の多対多）→ 将来。
- クラス/関数単位の単元（057/061）。
- 学習コンテンツ自体の自動生成の高度化（035 の範囲）。

## 参考
- 052（features/feature_files）/ 053（quiz KC 認定）/ 054（機能ベースラインクイズ・機能展開）/
  055（機能 KC ロールアップ・`granularity`）/ 056（粒度切替 UI）/ 035（学習プラン生成）。
- 既存: `frontend/src/routes/[org]/[project]/learning/+page.svelte`（統合ハブ）、
  `backend/api/app/services/debt_query.py`（機能ロールアップ）、`backend/api/app/api/v1/learning.py` / `quizzes.py`。
- 規約: `CLAUDE.md`（Svelte 5 runes・snake_case 配信・Annotated DI 順序・i18n ja/en・CHANGELOG 日本語）。
