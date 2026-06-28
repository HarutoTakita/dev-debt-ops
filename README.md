# DevDebtOps — 理解負債を「実測して返済」する Knowledge Debt Twin Agent

**理解負債（Knowledge / Understanding Debt）** — “コードは動くが、誰もその中身を本当には理解していない” 状態 —
を主役に据えたプラットフォーム。差別化は、理解度を `git blame` から*推測*するのではなく、**クイズで能動的に実測**し
（blame 非依存。単独開発でも、コードを書かない PM でも計測可）、**学習プラン → クイズ再受験で返済する閉ループ**を回すこと。
解析の中核には **Google ADK の Twin Agent** を据える。コード負債（技術負債）の検知・二軸マトリクスは維持するが、主役ではなく
**「どの理解ギャップが緊急かを示すホットスポット（リスク信号）」**として位置づける。

> Findy「**DevOps × AI Agent Hackathon**」提出作品。Google Cloud（Cloud Run）+ Gemini / ADK を中核に、
> AI エージェントとフルサイクル DevOps を実装している。

## スタック

- **フロントエンド** — SvelteKit 2（SPA・Svelte 5 runes）/ shadcn-svelte / Tailwind CSS v4 / Zod v4 / Paraglide 2.0（日本語・英語）。パッケージ管理は **bun**
- **バックエンド** — FastAPI / SQLModel / SQLAlchemy 2.0 (async) / Alembic / fastapi-users（JWT + Cookie）。Python 3.13、**uv workspace モノレポ**（`shared` / `api` / `service`）
- **データベース** — PostgreSQL 17（pgvector 拡張）
- **AI** — Google **Gemini**（Vertex AI 経由・ADC 認証）+ Google **ADK**（Agent Development Kit）
- **インフラ** — **Google Cloud**（Cloud Run / Cloud SQL / Cloud Tasks / Secret Manager / Cloud Armor / Artifact Registry / Workload Identity Federation / Monitoring）。**Terraform** で管理

## クイックスタート

```sh
cp .env.example .env.dev          # 初回のみ
docker compose watch              # PostgreSQL + api(:8000) + service（コード同期）
cd frontend && bun run dev        # 別ターミナル: Vite HMR on :5173（/api を :8000 にプロキシ）
```

ブラウザで <http://localhost:5173> を開く。

| サービス | URL |
| --- | --- |
| フロントエンド（Vite HMR） | http://localhost:5173 |
| バックエンド API | http://localhost:8000 |
| API ドキュメント（Scalar） | http://localhost:8000/api/docs |
| pgAdmin（`docker compose --profile tools up`） | http://localhost:5050 |

### 本番モードのローカル確認（3 レプリカ + Traefik）

```sh
docker compose -f compose.prod.yml up --build   # api(3) + service(2) + Traefik on :8080
open http://localhost:8080                       # Traefik → api がビルド済み SPA と /api の両方を配信
```

## リポジトリ構成

```text
.
├── frontend/        SvelteKit 2 SPA（bun, Vite, Tailwind v4, Paraglide）
│   └── screenshots/ 画面の自動スクリーンショット取得（取扱説明書のベース）
├── backend/         uv workspace モノレポ
│   ├── shared/      共有 enum・pydantic スキーマ・キュー/Blob Protocol・ORM モデル(Job)
│   ├── api/         FastAPI（外部公開 Cloud Run・DB/マイグレーション所有）
│   └── service/     重い処理 worker（内部 Cloud Run・Cloud Tasks ターゲット・ADK/Gemini）
├── infra/           Terraform
│   ├── gcp/         アプリスタック（Cloud Run / Cloud SQL / Cloud Tasks / LB / Cloud Armor 等）
│   └── bootstrap/   初回 bootstrap（WIF プール・デプロイ SA・tfstate バケット）
├── docker/          Dockerfile（api / service、各 dev / runtime ステージ）
├── docs/            ドキュメント（issue / 取扱説明書 / インフラ図）
├── compose.yml      開発スタック（db + api + service）
├── compose.prod.yml 本番モードのローカル確認用（Traefik）
└── CLAUDE.md        開発ガイドライン（最新・権威）
```

## 開発

```sh
# フロントエンド（frontend/）
bun run dev          # 開発サーバー
bun run check        # 型チェック（svelte-check）
bun run lint         # prettier + eslint
bun run test         # vitest 単体 + Playwright e2e

# バックエンド（backend/）。docker compose watch がコードを同期する
uv run --directory api pytest                                  # テスト（api は Postgres の test DB が必要）
uv run ruff check shared/shared api/app service/service        # リント
uv run ty check shared/shared api/app service/service          # 型チェック
```

- **プリコミット**: lefthook（ruff check / ruff format / prettier / eslint / gitleaks）。`./frontend/node_modules/.bin/lefthook install` で導入。フックはバイパスしない。

## CI / CD（GitHub Actions）

| ワークフロー | 内容 |
| --- | --- |
| `ci.yml` | backend（ruff + ty + pytest）/ frontend（prettier + eslint + svelte-check + vitest）。push + 非 draft PR |
| `deploy-stg.yml` | `develop` への push → Google Cloud staging へデプロイ |
| `deploy-prod.yml` | `v*.*.*` タグ → 本番デプロイ（承認必須） |
| `release.yml` | `v*.*.*` タグ → CHANGELOG 検証 + GitHub Release |
| `pr-review.yml` | **Gemini による PR 自動レビュー**（Google 公式 `run-gemini-cli`。PR 作成時 + `@gemini-cli /review` コメント。WIF + 最小権限 SA で Vertex AI を呼ぶ） |

イメージは Trivy で CRITICAL/HIGH の CVE をスキャンしてからデプロイ。認証は **Workload Identity Federation**（長期鍵不使用）。

## ドキュメント

- [`CLAUDE.md`](./CLAUDE.md) — 開発ガイドライン（最新・権威）。スタック・規約・運用の詳細はここ
- [`docs/issue/`](./docs/issue/) — 設計・意思決定の履歴（058/059 知識負債ファーストへのリポジション、069 ADK Twin Agent 中核化 ほか）
- [`docs/取扱説明書/`](./docs/取扱説明書/) — 画面ベースの取扱説明書（`frontend/screenshots/` で自動取得した画像が素材）
