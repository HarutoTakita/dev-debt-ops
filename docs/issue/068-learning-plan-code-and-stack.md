# issue 068: 学習プランを「コード具体」＋「技術スタック一般」の2本立てに再設計

## 概要
現状の学習プランは「チーム内資産（＝未読ファイルを確認させる動線）＋ gap-concept ベースの外部リンク」で、
実際に学ぶ中身が薄い。これを次の2セクションに再設計する。

- **A.「このコードを理解する」（具体）**: このリポジトリのソースコードを理解するための具体的な学習プラン。
- **B.「技術スタックを学ぶ」（一般）**: テックスタック解析で検出した言語/フレームワーク/DB の一般的な学習プラン。

## 背景・目的
- 現状はリンクの羅列で「学ぶ教材」が薄い、という指摘。
- 素材は既にある: 機能クラスタリング（`Feature`: 名前/説明/構成ファイル）と テックスタック解析（`tech_stack` テーブル）。
  これらを使い「具体（自分のコード）」「一般（技術）」の2軸で学べるようにする。

## 対応方針

### データ（Alembic マイグレーション）
- `learning_resources` に列を追加:
  - `section: str`（`"code"` | `"stack"`、default `"code"`）— どちらの学習プランに属するか。
  - `summary: str`（説明テキスト、default `""`）— 「何を・なぜ理解すべきか」の生成テキスト。

### バックエンド（service: `learning_plan_generation`）
- **セクション A（code）**: 機能クラスタリングの機能（`name`/`description`/構成ファイル、必要に応じ代表ファイルの抜粋）を
  Gemini に渡し、「このコードを理解する学習ステップ」を生成。各ステップ＝ `title`/`source_ref`（ファイル）/`summary`、
  `section="code"`。リンクはリポジトリビューア（ソース詳細）。
- **セクション B（stack）**: プロジェクトの `tech_stack`（言語/フレームワーク/DB）を Gemini に渡し、各技術の一般学習リソース
  （外部 URL ＋ `summary`）を生成。`section="stack"`。
- `gemini_stack_service` にプロンプトを2種追加（コード理解ステップ / 技術スタック学習）。
- `plan_generator` は両セクションを `learning_resources`/`learning_steps` に書き出し、`estimated_total_minutes` を集計。

### フロントエンド
- `learningResourceSchema` に `section` / `summary` を追加。
- `resource-list.svelte` を `origin`(team/external) ではなく `section`(code/stack) で分割表示。見出しを
  「このコードを理解する」「技術スタックを学ぶ」に。
- `resource-card.svelte` に `summary` を表示。リンクは A=ソース詳細、B=外部 URL（既存ロジックを踏襲）。
- i18n（ja/en）に新セクション見出し等を追加。旧 `learning_team_heading` / `learning_external_heading` を更新/置換。

## タスク
- [ ] Alembic: `learning_resources` に `section` / `summary` を追加
- [ ] shared model `LearningResource` に `section` / `summary`
- [ ] service: セクション A 生成（機能 → コード理解ステップ、Gemini）
- [ ] service: セクション B 生成（tech_stack → 技術学習、Gemini）
- [ ] service: `plan_generator` で両セクションを保存
- [ ] api: `LearningResourceOut` / `_plan_out` に `section` / `summary`
- [ ] frontend: schema / resource-list / resource-card / i18n
- [ ] tests: service（生成）/ api（配信形）/ frontend（type/lint/unit）

## 完了条件
- 学習プランが「このコードを理解する」「技術スタックを学ぶ」の2セクションで表示される。
- A は機能/ファイルに紐づく具体的な説明つきステップ、B は検出技術の一般学習リソース（外部リンク）。
- 各カードに説明（summary）が表示され、A はソース詳細、B は外部ページへ遷移できる。
- backend（ruff/ty/pytest）・frontend（check/lint/test）が通る。

## 非対象（将来）
- 学習進捗の高度なトラッキング、A/B 間の依存最適化。
- ソースコードの逐次解説（行単位の注釈）。本 issue は機能/ファイル単位の説明まで。
