# API リファレンス（OpenAPI）

DevDebtOps の外部 API（FastAPI）の OpenAPI 3.1 スキーマと、その閲覧用ドキュメントです。

- **スキーマ（JSON）**: [`openapi.json`](./openapi.json)
- **スキーマ（YAML）**: [`openapi.yaml`](./openapi.yaml)
- **スタンドアロン閲覧**: [`api.html`](./api.html) — ブラウザで直接開くと `openapi.json` を読み込み、API リファレンス（Scalar）を表示（アプリ起動不要）。

## 概要

- **ベース URL / プレフィックス**: すべてのアプリ API は `/api/v1/`（ヘルスチェックは `/api/v1/health` 系）。
- **OpenAPI バージョン**: 3.1.0
- **認証**: Cookie ベース（`APIKeyCookie`）。fastapi-users による access(JWT) + refresh(DB-backed) の Cookie 分離。詳細は `CLAUDE.md`「認証」節を参照。
- **更新系は PATCH（部分更新）**を使用（プロジェクト規約）。

## エンドポイント・グループ（タグ別オペレーション数）

| タグ | 数 | 概要 |
|---|---|---|
| `orgs` | 11 | 組織（テナント）管理 |
| `users` | 9 | ユーザー管理 |
| `quizzes` | 9 | クイズ生成・受験・再テスト |
| `debts` | 7 | コード負債（技術負債）一覧・詳細・改善 |
| `learning` | 6 | 学習プラン・ウォークスルー |
| `projects` | 5 | プロジェクト（リポジトリ接続） |
| `overview` | 5 | ダッシュボード（理解度×品質の俯瞰・推移） |
| `auth` | 4 | ログイン・リフレッシュ・ログアウト |
| `Health` | 4 | liveness / readiness |
| `GitHub` | 4 | GitHub 連携（App / Webhook） |
| `code-graph` | 3 | 依存グラフ（CodeGraphContext） |
| `galaxy` | 2 | 理解度マップ（ノード‐リンクグラフ） |
| `knowledge-units` | 2 | 理解ユニット（学習の単元） |
| `Stack` | 2 | 技術スタック検出 |
| `agentic` / `kc` / `features` / `jobs` / `Config` | 各 1 | エージェント解析実行 / 理解度計測 / 機能クラスタ / 非同期ジョブ状態 / 公開設定 |

（合計 76 オペレーション / 63 パス。正確な入出力スキーマは `openapi.json` / `api.html` を参照。）

## 閲覧方法

1. **このディレクトリの `api.html` をブラウザで開く**（最も手軽。オフライン可）。
   ローカルで開けない場合は簡易サーバー経由: `cd docs/reference && python3 -m http.server 8890` → `http://localhost:8890/api.html`。
2. **アプリ起動中の Scalar UI**: 開発環境で `/api/docs`（`scalar-fastapi`）。本番では無効。
3. **スキーマを直接**: `openapi.json` / `openapi.yaml` を Swagger Editor・Redoc・Postman 等に読み込む。

## 再生成

ルートやスキーマ（Pydantic モデル）を変更したら、以下で `openapi.json` / `openapi.yaml` を更新する（DB・ネットワーク不要）。

```bash
cd backend && uv run --directory api python -m app.scripts.export_openapi
```

生成スクリプト: `backend/api/app/scripts/export_openapi.py`。
