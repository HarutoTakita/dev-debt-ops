# Rosetta — Tech Debt Twin Agent

## プロジェクト概要
SvelteKit (SPA)、FastAPI、PostgreSQL、Docker、Terraformを使用した、Google Cloud ベースのフルスタックアプリケーション。

## モノレポ構成
- `frontend/` — SvelteKit 2 SPA (Svelte 5 runes, shadcn-svelte@latest, Tailwind v4)
- `backend/` — FastAPI バックエンド (Python 3.13, SQLModel, Alembic)
- `infra/` — Terraform (Google Cloud Run + Cloud SQL)
- `docker/` — Dockerfiles (dev + prod)
- `docs/` — ドキュメント (Diátaxis: `tutorials/` / `guides/` / `reference/` / `adr/`)

## フロントエンド (`frontend/`)
- **スタック:** SvelteKit 2 + Svelte 5 + shadcn-svelte@latest + Tailwind CSS v4 + Zod v4
- **SPAモード:** `adapter-static` with `fallback: 'index.html'`, `export const ssr = false`
- **パッケージマネージャー:** bun
- **開発サーバー:** `cd frontend && bun run dev` (ポート 5173)
- **ビルド:** `cd frontend && bun run build` -> `frontend/build/` に出力
- **単体テスト:** `cd frontend && bun run test:unit` (vitest with browser-mode + node dual projects)
- **全テスト:** `cd frontend && bun run test` (vitest + Playwright e2e — ブラウザのインストールが必要)
- **リント:** `cd frontend && bun run lint` (prettier --check + eslint)
- **型チェック:** `cd frontend && bun run check` (svelte-check)
- **フォーマット:** `cd frontend && bun run format` (prettier --write)
- **Svelte 5 runes のみ** — レガシーな `$:` や `writable()` stores は使用しない
- **shadcn-svelte@latest:** コンポーネントは `frontend/src/lib/components/ui/` 内
- **SSR ルートなし:** `+page.server.js`、`+layout.server.js`、`+server.js` ファイルなし
- **Vite プロキシ:** 開発時に `/api` を `http://localhost:8000` にプロキシ (`vite.config.ts` 参照)
- **フロントエンドバリデーション:** `src/lib/api/schemas.ts` の Zod v4 スキーマですべてのAPIレスポンスを解析 (snake_case フィールドはそのまま保持 — camelCase変換はまだなし)
- **i18n:** Paraglide 2.0 — 日本語（プライマリ）、英語（セカンダリ）

## バックエンド (`backend/`)
- **スタック:** FastAPI + SQLModel + SQLAlchemy 2.0 async + PostgreSQL + Alembic
- **Python:** 3.13、`uv` で管理
- **開発サーバー:** `docker compose up` (コンテナ化されたバックエンド、ポート8000)
- **テスト:** `cd backend && uv run pytest`
- **リント:** `cd backend && uv run ruff check app/ && uv run ruff format --check app/`
- **型チェック:** `cd backend && uv run ty check`
- **APIプレフィックス:** `/api/v1/`
- **API ドキュメント:** `/api/docs` の Scalar (本番では無効)、`scalar-fastapi` を使用
- **Annotated DI param 順序は重要:** `Annotated[T, Depends(f)]` deps を編集する際（例：`app/api/deps.py`）、パラメーターの順序を変更しない。FastAPIはAnnotated下でも宣言順序で依存性を解決する；順序変更により pytest teardown 中にプールスロットの競合 → DROP TABLE で `DeadlockDetectedError` が発生する。構文移行時は元の順序を保持する。
- **認証:** fastapi-users with access (JWT, 5分) + refresh (DB-backed, 7日) cookieの分離；再利用検出付きローテーション；`users.token_epoch` は即座のログアウト無効化を強制。レート制限は**エッジで強制**、アプリ内ではない — 本番環境では Cloud Armor で同等の設定が必要。
- **AI:** `google-generativeai` (Gemini API) + Google ADK (Agent Development Kit)

## 開発ワークフロー
```
cp .env.example .env.dev         # 初回のみ — docker-compose に必要
docker compose watch             # Postgres + backend
docker compose --profile tools up  # pgAdmin を :5050 で含める（オプション）
cd frontend && bun run dev       # ネイティブVite HMR on :5173, /api を :8000 にプロキシ
```

### 本番モードローカルスタック (3レプリカ + Traefik)
```
docker compose -f compose.prod.yml up --build   # 本番Dockerfileが SPA をバックエンドに焼き込む；3レプリカ、Traefik on :8080
open http://localhost:8080                      # バックエンドがビルド済みSPAと/apiの両方を配信
```
Traefikダッシュボードは :8081。`Dockerfile.prod` が `bun run build` を実行し、静的バンドルを `app/static` にコピー、`main.py` が `ENVIRONMENT=prod` の時に `/` にマウントする。

## コードスタイル
### フロントエンド (TypeScript/Svelte)
- スペース（タブでない）、ダブルクォート、末尾カンマ、119文字の印刷幅
- Prettier + eslint 強制 — コミット前に `format` を実行

### バックエンド (Python)
- 4スペースインデント、ダブルクォート、120文字行長
- Ruff でリント + フォーマット — コミット前に `ruff check --fix && ruff format` を実行

## 重要事項
- **最新のベストプラクティスを使用** — 常にスタックの最新ドキュメントを参照 (Svelte 5, SvelteKit 2, Tailwind CSS v4, Zod v4, FastAPI, SQLModel, Pydantic v2, Google ADK)。コード例にはcontext7 MCPを使用；公式ドキュメントを直接検索。
- **警告を無視しない** — コンパイラ警告、リンター警告、廃止予定通知をエラーとして扱う。即座に修正。

## 規約
- **ファイル命名:** フロントエンドの全ファイル・フォルダはkebab-case；PythonはPythonはsnake_case
- **コンポーネント:** `frontend/src/lib/components/<domain>/` 内のkebab-case `.svelte` ファイル
- **ストア:** Svelte 5 クラスベース runes パターンを使用した `*.svelte.ts` ファイル
- **PATCH** をすべての更新操作に使用（部分更新）
- **チェンジログ:** `CHANGELOG.md`（日本語）— [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)フォーマットに従う；セクションキーワード（`Added`/`Changed`/`Deprecated`/`Removed`/`Fixed`/`Security`）は英語のまま。`vX.Y.Z` タグをプッシュ前に `[Unreleased]` 下に `## [X.Y.Z] - YYYY-MM-DD` セクションを追加 — Releaseワークフローがノートを抽出し、マッチするセクションがなければ失敗。

## インフラストラクチャ
- **クラウド:** Google Cloud Platform
- **アプリケーション実行:** Cloud Run（Webhook 駆動・自動スケール・コンテナ化）
- **非同期ジョブ:** Cloud Functions（定期スキャン・Pub/Sub トリガー）
- **データベース:** Cloud SQL (PostgreSQL)
- **シークレット:** Secret Manager（プレーンテキスト環境変数は絶対不可）
- **コンテナレジストリ:** Artifact Registry
- **認証:** Workload Identity Federation（long-lived credentials 不使用）
- **レート制限:** Cloud Armor（エッジで強制）
- **pgAdmin:** `docker compose --profile tools up` でオプトイン（デフォルトでは起動しない）

## 注意点
- **Tailwind v4:** `@tailwindcss/vite` プラグインを使用、PostCSS、`tailwind.config.js` なし
- **`@theme inline` not `@theme`:** shadcn-svelte@latest の Tailwind v4 トークン登録に必要
- **`tailwindcss()` before `sveltekit()`:** `vite.config.ts` のプラグイン順序が重要
- **Paraglide 2.0:** フレームワーク非依存Viteプラグイン、明示的な `strategy: ["url", "cookie", "baseLocale"]`
- **`paths.relative = false`:** ロケールプレフィックス付きURLでの正しいアセットパスのためにsvelte.config.jsで必要
- **hooks.server.ts は意図的に存在:** SPA モードは実行時にSSRを使用しないものの、`vite dev` 中のParaglideの `%paraglide.lang%` プレースホルダー解決に必要
- **Vitest browser-mode:** テストはデュアルプロジェクト設定を使用 — `.svelte.spec.ts` 用の `client`（Playwright経由ブラウザ）と通常の `.spec.ts` 用の `server`（node）
- **docker-compose は `.env.dev` が必要:** 初回実行前に `.env.example` からコピー
- **`frontend/src/lib/components/ui/` は読み取り専用:** shadcn-svelte プリミティブは相互に合成される（FieldがInput/Label/Textareaをラップする等）ため、ベースプリミティブの編集は全合成を静かに破壊；`shadcn-svelte add --overwrite` もローカル編集を上書きする。`ui/` *外* のラッパーコンポーネントで生成されたものを合成し、`$lib/utils.ts` の `cn` でクラスをマージしてカスタマイズ。より深いカスタマイズには、`bits-ui` に対して新規作成。

## プリコミットフック
- **lefthook** (`frontend/package.json` 経由でインストール、フックのインストール: `./frontend/node_modules/.bin/lefthook install`)
- 並列プリコミットチェックを実行: ruff check, ruff format, prettier, eslint
- **フックをバイパスしない** — 代わりに根本的な問題を修正

## CI
- **GitHub Actions** (`.github/workflows/ci.yml`): push + 非draft PRで実行
  - `check-backend` — ruff check + format + ty check
  - `test-backend` — Postgres 17 サービスコンテナでpytest
  - `lint-frontend` — prettier + eslint + svelte-check（別ステップ）
  - `test-frontend` — vitest単体テスト（browser-mode chromium、実行間でキャッシュ）
- **Deploy stg** (`.github/workflows/deploy-stg.yml`): `develop` へのpush — ビルド → Google Cloud へデプロイ
- **Deploy prod** (`.github/workflows/deploy-prod.yml`): タグ `v*.*.*` のpush — ビルド → Google Cloud へデプロイ（承認必須）
- **Release** (`.github/workflows/release.yml`): タグ `v*.*.*` のpush — `CHANGELOG.md` 見出しをリント、GitHub Release作成
- **E2E** (`.github/workflows/e2e.yml`): 手動トリガー（workflow_dispatch）
