# リポジトリのテックスタックを解析する

## 概要

接続済みリポジトリを解析し、使用されている言語・フレームワーク・インフラ・認証認可・DB など
の技術スタックを自動抽出して表示する。
Knowledge Debt Agent がクイズ生成や KC 算出を行う際の前提情報となる。

## 背景・目的

ナレッジ負債の評価（KC 算出・クイズ生成）には「このリポジトリが何を使っているか」の把握が
不可欠である。例えば Docker を採用しているプロジェクトで「コンテナ化を理解しているか」を
問うクイズを生成するには、事前にそのリポジトリがコンテナ化されていることを知っている必要がある。

本 issue では、まず **単発 API 呼び出し** で Gemini にテックスタック分析を依頼するシンプルな
実装を行う。将来的には **ADK エージェントが定期的に・自律的に** リポジトリを解析し、
ファイルの変更検知をトリガーとしてスタック情報を自動更新する構成に移行する（後述の将来拡張を参照）。

## タスク

### バックエンド

#### DB マイグレーション
- [ ] `tech_stacks` テーブルを追加する
  ```
  id, owner, repo, branch, analyzed_at,
  languages: JSON,  -- [{ name, confidence }]
  categories: JSON  -- { frameworks, databases, auth, container, infra, cicd, monitoring, ... }
  ```

#### API（`backend/app/api/v1/stack.py`）
- [ ] `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack`
  - 処理フロー:
    1. GitHub API でリポジトリの主要ファイルを取得
       （`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`,
         `Dockerfile`, `compose.yml`, `.github/workflows/*.yml`,
         `*.tf`, `*.bicep`, `k8s/*.yaml`, `requirements.txt` など）
    2. ファイル内容を Gemini API に渡してテックスタックを分類
    3. 結果を `tech_stacks` テーブルに保存（同一 owner/repo は上書き）
    4. 分析結果を返却

- [ ] `GET /api/v1/github/repositories/{owner}/{repo}/stack`
  - DB に保存済みの最新スタック情報を返す
  - 未分析の場合は 404

- [ ] `router.py` に `stack_router` を追加する

#### Gemini プロンプト設計
- [ ] 以下カテゴリを JSON で出力するプロンプトを設計する

  | カテゴリ | 検出対象の例 |
  |---|---|
  | `languages` | TypeScript, Python, Go, Rust, Java |
  | `frameworks` | SvelteKit, FastAPI, React, Next.js, Express |
  | `databases` | PostgreSQL, MySQL, Redis, MongoDB, Firestore |
  | `auth` | JWT, OAuth2, Auth0, Supabase Auth |
  | `container` | Docker, Kubernetes, Docker Compose |
  | `infra` | Terraform, GCP, AWS, Azure, Pulumi |
  | `cicd` | GitHub Actions, CircleCI, Cloud Build |
  | `monitoring` | Cloud Logging, Prometheus, Datadog, Sentry |
  | `testing` | Vitest, pytest, Jest, Playwright |
  | `other` | その他の主要ライブラリ・ツール |

  各技術に `confidence: "high" | "medium" | "low"` を付与する。

### フロントエンド API クライアント
- [ ] `techStackSchema` を `frontend/src/lib/api/schemas.ts` に追加する
- [ ] `analyzeStack(owner, repo)` と `getStack(owner, repo)` を `client.ts` に追加する

### フロントエンド UI
- [ ] `TechStackPanel` コンポーネントを実装する
  （`frontend/src/lib/components/repo/tech-stack-panel.svelte`）
  - カテゴリごとにバッジで技術を表示
  - 「解析する」ボタン → ローディング → 結果表示
  - 最終解析日時を表示
- [ ] リポジトリ接続後の画面（`[org]/+page.svelte`）にパネルを組み込む
  - ファイルツリーの上部 or サイドパネルに配置

## 完了条件

- `POST /api/v1/github/repositories/{owner}/{repo}/analyze-stack` が
  テックスタック情報を JSON で返すこと
- 返却スキーマが上記カテゴリ構造に準拠すること
- フロントエンドで「解析する」ボタン押下後にテックスタックが表示されること
- 解析結果が DB に保存され、再訪問時に `GET` で即座に取得できること

## API レスポンス形式

```json
// POST または GET /api/v1/github/repositories/{owner}/{repo}/stack
{
  "owner": "HarutoTakita",
  "repo": "my-app",
  "branch": "main",
  "analyzed_at": "2026-05-13T10:00:00+09:00",
  "languages": [
    { "name": "TypeScript", "confidence": "high" },
    { "name": "Python", "confidence": "high" }
  ],
  "categories": {
    "frameworks": [
      { "name": "SvelteKit", "confidence": "high" },
      { "name": "FastAPI", "confidence": "high" }
    ],
    "databases": [
      { "name": "PostgreSQL", "confidence": "high" }
    ],
    "auth": [
      { "name": "JWT", "confidence": "high" },
      { "name": "GitHub OAuth", "confidence": "medium" }
    ],
    "container": [
      { "name": "Docker", "confidence": "high" },
      { "name": "Docker Compose", "confidence": "high" }
    ],
    "infra": [
      { "name": "Terraform", "confidence": "medium" },
      { "name": "GCP Cloud Run", "confidence": "medium" }
    ],
    "cicd": [
      { "name": "GitHub Actions", "confidence": "high" }
    ],
    "monitoring": [],
    "testing": [
      { "name": "pytest", "confidence": "high" },
      { "name": "Vitest", "confidence": "high" }
    ],
    "other": [
      { "name": "Alembic", "confidence": "high" },
      { "name": "SQLModel", "confidence": "high" }
    ]
  }
}
```

## 将来拡張（ADK エージェント化）

現在の実装はユーザーが「解析する」ボタンを押した際の単発 API 呼び出しである。
将来的には以下の形に移行する。

### エージェント化の方針

```
[トリガー]
  - リポジトリ接続時に自動実行
  - GitHub Webhook: push イベント（主要ファイル変更時）
  - 定期スキャン: Cloud Scheduler → Cloud Functions → Pub/Sub

[Stack Analysis Agent (ADK)]
  Tool: list_key_files()       — 解析対象ファイルの列挙
  Tool: read_file_content()    — GitHub API でファイル取得
  Tool: classify_with_gemini() — Gemini でカテゴリ分類
  Tool: diff_with_previous()   — 前回結果との差分検出
  Tool: save_stack()           — DB 保存・変更通知

[自律ループ]
  変更検知 → 差分のみ再分析 → 技術スタックを最新に維持
  新技術追加を Knowledge Debt Agent に通知
  （「Terraform が追加されました。関連メンバーのKCを確認しますか？」）
```

### 現実装との差分

| 項目 | 現実装（MVP） | 将来実装 |
|---|---|---|
| トリガー | ユーザーが手動で「解析する」 | Webhook / 定期スキャン |
| 実行場所 | FastAPI リクエストハンドラ内 | ADK エージェント（Cloud Run / Functions） |
| ファイル取得 | 固定ファイルリスト | エージェントが自律的に決定 |
| 差分管理 | なし（全量上書き） | 前回比較・変更分のみ再解析 |
| 通知 | なし | Knowledge Debt Agent へのイベント発行 |
