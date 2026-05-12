---
name: release-version
description: バックエンド + フロントエンド全体でバージョンをバンプし、日本語のチェンジログを更新、ロックファイルを更新
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
   - 各箇条書き: `- <emoji> **短いタイトル。** 説明。 ([#NN](url))` — PRを参照。
   - 内部/インフラ/テスト修正はコミットリンク付きの単一箇条書きにクラスター。
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

7. **検証:**
   - `backend/pyproject.toml`、`frontend/package.json`、`backend/uv.lock`、`frontend/bun.lock` にバージョンが表示される。
   - `CHANGELOG.md` に新しい `## [X.Y.Z] - YYYY-MM-DD` セクションがある。
   - オプションのスモークテスト: `./scripts/extract-changelog.sh X.Y.Z` が空でないノートを出力。

## 重要な注意事項

- `CHANGELOG.md` を日本語で作成・更新。`scripts/extract-changelog.sh` が読み取る。
- チェンジログフォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に従う。セクションキーワード（`Added`/`Changed`/`Deprecated`/`Removed`/`Fixed`/`Security`）と `[Unreleased]` は英語のまま — パーサーツールが正確なトークンに依存。
- `vX.Y.Z` タグをプッシュする*前に*チェンジログセクションが存在することを確認。
- **自動的にコミットやタグをしない** — コミットとタグプッシュのタイミングはユーザーが決定。