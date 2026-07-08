---
name: release-version
description: バックエンド + フロントエンド全体でバージョンをバンプし、日本語のチェンジログを更新、ロックファイルと API/ER 図ドキュメント（docs/reference）を再生成、取扱説明書をエージェント支援で更新
---

ユーザー入力では対象バージョンと、何を強調するかのオプションのノートを指定できます。

ユーザー入力:

$ARGUMENTS

## 手順

1. **バンプするバージョンを決定。** ユーザーがバージョン（例：`0.1.0`）を提供した場合はそれを使用。そうでなければ確認。`0.0.x` の1.0未満バージョンは `release.yml` によってプレリリースとして自動マーク；`0.1.0+` は正式リリース。

2. **前回のリリースタグからの変更を収集:**
   - `git tag --list 'v*.*.*' --sort=-v:refname | head -1` を実行して前回のリリースタグを検索。
   - タグが存在しない場合（初回リリース）、すべてのコミットに `git log --oneline --no-merges` を使用。
   - そうでなければ: `git log <前回タグ>..HEAD --oneline --no-merges`。
   - `gh pr list --state merged --base develop --json number,title,mergedAt` を実行し、タグ日付後にマージされたPRでフィルタ。
   - 可能な限り各コミットを親PRにマップ。生のコミットハッシュよりPR参照を優先。
   - `git remote get-url origin` からリポジトリURLを取得してPR/コミットリンク用（ハードコードしない）。

3. **`CHANGELOG.md` のフォーマットに従ってチェンジログエントリを下書き:**
   - Keep a Changelog セクションを使用: `### Added`、`### Changed`、`### Deprecated`、`### Removed`、`### Fixed`、`### Security`。これらのキーワードは英語のまま。
   - 各箇条書きは**日本語の簡潔な説明文**（絵文字プレフィックスは付けない）。冒頭に要点を置き、要点となる語句は**インライン太字**で強調する（例: `- 〇〇を**△△**に刷新。…詳細…`）。必要に応じて `: ` の後に詳細を続ける。
   - 関連する PR / issue があれば参照する: マージ済み PR は末尾に `([#NN](url))`、issue は本文に `（issue NN）`。直接コミットで PR が無い変更は参照を省略してよい（無理に付けない）。
   - 内部/インフラ/テスト修正は**単一箇条書きにまとめる**（可能ならコミット/PR リンク付き）。
   - 作成前に下書きをユーザーに表示し、確認を求める。

4. **チェンジログを作成:**
   - `CHANGELOG.md` — 日本語でエントリを作成。リポジトリの散文スタイルに合わせてだ/である調を使用。
   - `## [Unreleased]` と前回のバージョン見出しの間に新しいセクションを挿入。
   - **見出しフォーマットは重要:** 正確に `## [X.Y.Z] - YYYY-MM-DD` である必要がある。`release.yml` は正規表現 `^## \[(Unreleased|N.N.N)\]( - YYYY-MM-DD)?$` でリント、`scripts/extract-changelog.sh` でセクションが見つからない場合 — Releaseワークフローが失敗。

5. **両方のパッケージファイルでバージョンをバンプ:**
   - `backend/pyproject.toml` — `version = "X.Y.Z"`。
   - `frontend/package.json` — `"version": "X.Y.Z"`。

6. **ロックファイルを更新:**
   - `cd backend && uv lock`
   - `cd frontend && bun install`

7. **API ドキュメント / DB ER 図を再生成（`docs/reference/`）:**
   - `cd backend && uv run --directory api python -m app.scripts.export_openapi` — `docs/reference/openapi.json`（OpenAPI 3.1）を更新。
   - `cd backend && uv run --directory api python -m app.scripts.export_dbml` — `docs/reference/schema.dbml`（DBML の ER 図）を更新。
   - どちらも DB・ネットワーク不要（ルート定義 / `SQLModel.metadata` から純粋に生成）。リリースに含まれるルート・スキーマ・DB モデルの変更をドキュメントへ反映する。
   - 差分が出た場合はバージョンバンプと同じコミットに含める（ドキュメントとコードの同期を保つ）。

8. **取扱説明書（`docs/取扱説明書/README.md`）をエージェント支援で更新:**
   このリリースに**ユーザー向け UI / 画面 / 操作の変更**が含まれる場合に実施（内部/インフラのみならスキップ可。迷う場合はユーザーに確認）。取扱説明書は「説明文＋スクリーンショット」で構成され、スクショは決定論的に再取得できるが、本文はモデル生成のため**コミット前に必ず人間がレビュー**する。

   a. **スクリーンショットを再取得**（`frontend/screenshots/` の Playwright ハーネス。詳細は同 README）:
      - 前提: デモモードのスタックを起動しデモデータを投入（`DEMO_MODE_ENABLED=true` で `docker compose watch` → `docker compose exec api uv run --directory api python -m app.scripts.seed_demo` → `cd frontend && bun run dev`）。
      - 実行: `cd frontend && bun run screenshots` → `docs/取扱説明書/images/screens/`・`images/screens-mobile/` と `screens.manifest.json` / `screens-mobile.manifest.json` を更新（PC 1440x900 / モバイル 390x844）。
      - スタック未起動・Playwright ブラウザ未導入などで実行できない場合はスキップし、その旨を記録（本文更新のみ手動で行う）。

   b. **本文をサブエージェントで更新**（Agent ツールで起動）。サブエージェントに以下を渡す:
      - このリリースのユーザー向け変更（手順3で作成したチェンジログの `Added` / `Changed` / `Removed`）。
      - `docs/取扱説明書/screens.manifest.json`（`key → { title, route, file }`）と `docs/取扱説明書/README.md`（既存）。
      - 指示: 変更に該当する節の説明文を更新し、新規画面は節を追加（manifest の `key`/`title`/`route` と `images/screens/<key>.png` を対応付け）、廃止画面の節と画像参照を削除する。文体・見出し構成・目次は既存 README に合わせ、**確認できない機能は書かない**（manifest とチェンジログにある事実のみ）。
      - 生成後、人間が差分をレビューしてからコミットに含める。

9. **検証:**
   - `backend/pyproject.toml`、`frontend/package.json`、`backend/uv.lock`、`frontend/bun.lock` にバージョンが表示される。
   - `CHANGELOG.md` に新しい `## [X.Y.Z] - YYYY-MM-DD` セクションがある。
   - `docs/reference/openapi.json` / `docs/reference/schema.dbml` が最新（再生成しても差分が出ない）。
   - ユーザー向け変更があった場合、`docs/取扱説明書/README.md` に反映済み（無ければスキップで可）。
   - オプションのスモークテスト: `./scripts/extract-changelog.sh X.Y.Z` が空でないノートを出力。

## 重要な注意事項

- `CHANGELOG.md` を日本語で作成・更新。`scripts/extract-changelog.sh` が読み取る。
- チェンジログフォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に従う。セクションキーワード（`Added`/`Changed`/`Deprecated`/`Removed`/`Fixed`/`Security`）と `[Unreleased]` は英語のまま — パーサーツールが正確なトークンに依存。
- `vX.Y.Z` タグをプッシュする*前に*チェンジログセクションが存在することを確認。
- **自動的にコミットやタグをしない** — コミットとタグプッシュのタイミングはユーザーが決定。