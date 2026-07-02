# 画面スクリーンショット自動取得（仕様書兼取扱説明書のベース）

DevDebtOps の各画面を Playwright で自動撮影し、`docs/取扱説明書/images/screens/` に PNG と
`docs/取扱説明書/screens.manifest.json`（ページのメタ情報）を出力する。これを入力に仕様書・取扱説明書を生成する。

認証は **ゲストデモログイン**（issue 069）を使うため GitHub アカウント不要。シード済みのデモ org
（`demo` / `sample-shop`）に対して読み取り中心で撮影する。

## 前提条件

撮影対象のスタックが起動しており、バックエンドでデモモードが有効・デモデータが投入済みであること。

1. **バックエンドをデモモードで起動**（`DEMO_MODE_ENABLED=true`）

   `.env.dev` に追記、または環境変数で渡す:

   ```sh
   echo "DEMO_MODE_ENABLED=true" >> .env.dev
   docker compose watch        # api(:8000) + service + db
   ```

2. **デモデータを投入**（冪等。API が参照する DB に対して実行）

   ```sh
   docker compose exec api uv run --directory api python -m app.scripts.seed_demo
   # 入れ直す場合: ... seed_demo reset
   ```

3. **フロントエンド開発サーバーを起動**（`/api` は :8000 にプロキシ）

   ```sh
   cd frontend && bun run dev   # :5173
   ```

## 実行

```sh
cd frontend
bun run screenshots            # :5173 を対象に全画面を撮影
bun run screenshots:headed     # ブラウザを表示して実行（デバッグ用）
```

本番モードのローカルスタック（`compose.prod.yml`、Traefik :8080）を対象にする場合:

```sh
BASE_URL=http://localhost:8080 bun run screenshots
```

## 出力

`bun run screenshots` は **PC 版**と**モバイル(レスポンシブUI)版**の 2 プロジェクトで撮影する（Playwright の
`projects`。振り分けは helpers がビューポート幅で自動判定）:

- PC 版（`desktop`, 1440x900）
  - 画像: `docs/取扱説明書/images/screens/<NN-key>.png`
  - メタ情報: `docs/取扱説明書/screens.manifest.json`（`key → { title, route, file, capturedAt }`）
- モバイル版（`mobile`, 390x844, isMobile）
  - 画像: `docs/取扱説明書/images/screens-mobile/<NN-key>.png`
  - メタ情報: `docs/取扱説明書/screens-mobile.manifest.json`

モバイルは主要ページ（`pages.spec` / `quiz.spec`）のみ撮影する。デスクトップ専用クローム（サイドバーの
ヘルプ/セクション、コマンドパレット ⌘K 等）を撮る `ui.spec` / `sidebar.spec` は mobile ではスキップする。
片方だけ撮る場合は `--project=desktop` / `--project=mobile` を付ける（例: `bun run screenshots -- --project=mobile`）。

## 撮影するページ

| key                   | ページ                                   | 取得方法                                                    | spec    |
| --------------------- | ---------------------------------------- | ----------------------------------------------------------- | ------- |
| `01-login`            | ログイン / お試しデモ入口                | 直接                                                        | helpers |
| `02-org-dashboard`    | 組織ダッシュボード                       | 直接                                                        | pages   |
| `03-overview`         | プロジェクト概要 / 解析コックピット      | 直接                                                        | pages   |
| `04-matrix`           | コード品質マップ（二軸マトリクス）       | 直接                                                        | pages   |
| `05-matrix-detail`    | 負債の詳細                               | 一覧の先頭を開く（best-effort）                             | pages   |
| `06-galaxy`           | 理解度マップ（マップ表示）               | 直接                                                        | pages   |
| `07-learning`         | クイズと学習（統合ハブ）                 | 直接                                                        | pages   |
| `08-learning-code`    | コード学習ウォークスルー                 | 「学習を開く」→ コード資源（best-effort）                   | pages   |
| `09-quiz-session`     | クイズ受験（集中モード）                 | 「理解度を確認する」（best-effort）                         | quiz    |
| `10-quiz-result`      | クイズ採点結果                           | 受験フローを辿る（best-effort）                             | quiz    |
| `11-repos`            | コード改善（ファイルツリー + 負債）      | `?path=` で指摘ファイルを開く（best-effort）                | pages   |
| `12-settings`         | プロジェクト設定                         | 直接                                                        | pages   |
| `13-galaxy-list`      | 理解度マップ（リスト表示）               | 「リスト」タブ（best-effort）                               | ui      |
| `14-help-menu`        | ヘルプメニュー（ドロップダウン）         | 「ヘルプ」クリック（best-effort）                           | ui      |
| `15-onboarding-tour`  | オンボーディングガイド（ツアー）         | ヘルプ →「オンボーディングガイドを確認する」（best-effort） | ui      |
| `16-changelog`        | 変更履歴（CHANGELOG）                    | ヘルプ →「バージョン」（best-effort）                       | ui      |
| `17-project-sections` | プロジェクトのセクション分け / スター    | localStorage に状態を投入（best-effort）                    | sidebar |
| `18-new-project`      | 新規プロジェクト作成（repo 選択）        | 「新規プロジェクト」→ repo 一覧（best-effort）              | ui      |
| `19-analysis-status`  | 解析ステータス（解析ラン・コックピット） | トップバー「解析」ポップオーバー（best-effort）             | ui      |
| `20-command-palette`  | コマンドパレット（⌘K 検索）              | ⌘K / Ctrl+K で開く（best-effort）                           | ui      |

> `/quizzes` は `/learning?tab=quiz` へ 308 リダイレクトされる統合ハブ（= `07-learning`）なので個別撮影はしない。
>
> 「best-effort」のページはシードデータ・UI に依存する。撮れない場合は warning ログを出してスキップし、
> 他のページ撮影は継続する。セレクタが変わった場合は各 spec を調整する。
>
> **サイドバーのセクション分け / スターは全画面に適用される**（`startDemo()` 内の `applyProjectSections` が
> 共通で localStorage に投入する）。`ui.spec.ts` / `sidebar.spec.ts` 専用ではなく全ショットのサイドバーに反映される。

## 構成

| ファイル               | 役割                                                                                                                                |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `playwright.config.ts` | 撮影専用設定（e2e とは独立。webServer なし・直列実行・ダーク・2x）                                                                  |
| `helpers.ts`           | `shot()`（撮影 + manifest 追記 + デモバナー除去）/ `startDemo()`（デモログイン + 全画面にセクション/スター適用）/ org・project 定数 |
| `pages.spec.ts`        | 主要ページ + 詳細ページ（負債詳細・コード学習・コード改善）                                                                         |
| `quiz.spec.ts`         | クイズ受験フロー                                                                                                                    |
| `ui.spec.ts`           | 理解度マップ list / ヘルプ / オンボーディング / 新規プロジェクト / 解析ステータス / 変更履歴                                        |
| `sidebar.spec.ts`      | サイドバーのセクション分け / スター                                                                                                 |

デモ org / project の slug は `backend/api/app/scripts/seed_demo.py`（`DEMO_ORG_SLUG` / `DEMO_PROJECT_SLUG`）と
`helpers.ts` の `ORG` / `PROJECT` を一致させること。

## デモ対応のためのアプリ拡張（issue 069 の延長）

一部画面はデモ（GitHub 非接続）でも撮れるよう、アプリ側をデモ対応に拡張している:

- **`backend/api/app/api/v1/github.py`** — repositories / branches / tree / contents を、デモユーザー時は
  seed（`CodeDebt` の file_path + code_snippet）から返す（`OptionalGitHubClientDep`）。これで「コード改善」の
  ファイルツリー（`11-repos`）と新規プロジェクトの repo 選択（`18-new-project`）がデモで動く。書き込み系・解析実行は
  従来どおりデモ不可。
- **`backend/api/app/scripts/seed_demo.py`** — `_EXTRA_PROJECTS` で複数プロジェクトを投入し、サイドバーの
  セクション分け / スター（`17-project-sections`）を再現できるようにした。
- 解析実行はデモでは無効（`19-analysis-status` は既存のステータス UI をそのまま撮る方針）。
