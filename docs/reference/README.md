# API リファレンス（OpenAPI）

DevDebtOps の API とデータベースのリファレンスです。

- **API スキーマ（OpenAPI 3.1 / JSON）**: [`openapi.json`](./openapi.json)
- **DB ER 図（DBML）**: [`schema.dbml`](./schema.dbml) — [dbdiagram.io](https://dbdiagram.io/d) に貼り付けるか `dbml-renderer` で ER 図として可視化できる。

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

（合計 76 オペレーション / 63 パス。正確な入出力スキーマは `openapi.json` を参照。）

## 閲覧方法

1. **アプリ起動中の Scalar UI**: 開発環境で `/api/docs`（`scalar-fastapi`）。本番では無効。
2. **スキーマを直接**: `openapi.json` を Swagger Editor・Redoc・Scalar・Postman 等に読み込む。

## 再生成

ルートやスキーマ（Pydantic モデル）を変更したら、以下で `openapi.json` を更新する（DB・ネットワーク不要）。

```bash
cd backend && uv run --directory api python -m app.scripts.export_openapi
```

生成スクリプト: `backend/api/app/scripts/export_openapi.py`。

## ER 図（DBML）の再生成

DB スキーマ（SQLModel のモデル）を変更したら、以下で `schema.dbml` を更新する（DB・ネットワーク不要。`SQLModel.metadata` から生成）。

```bash
cd backend && uv run --directory api python -m app.scripts.export_dbml
```

生成スクリプト: `backend/api/app/scripts/export_dbml.py`。マイグレーション（`api` 所有）と ORM モデルが真実で、DBML はその可視化用スナップショット。
