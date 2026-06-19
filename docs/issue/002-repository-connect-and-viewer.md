# リポジトリ接続とコンテンツビューアを実装する

## 概要

GitHub API エンドポイント（リポジトリ一覧・ブランチ一覧・ファイルツリー・ファイル内容）を実装し、フロントエンドでリポジトリを選択・接続してファイルを閲覧できる UI を構築する。

## 背景・目的

Rosetta のコード負債検知はリポジトリ内のファイルを読み取ることで成立する。本 issue ではユーザーがリポジトリを選択し、そのファイル構造を確認できるところまでを一通り実装する。

## タスク

### バックエンド API（`backend/app/api/v1/github.py`）
- [ ] `GET /api/v1/github/repositories?page=&per_page=` — リポジトリ一覧（ページネーション付き）
- [ ] `GET /api/v1/github/repositories/{owner}/{repo}/branches` — ブランチ一覧
- [ ] `GET /api/v1/github/repositories/{owner}/{repo}/tree?branch=` — ファイルツリー（再帰）
- [ ] `GET /api/v1/github/repositories/{owner}/{repo}/contents?path=&ref=` — ファイル内容
- [ ] `router.py` に `github_router` を追加する

### フロントエンド API クライアント
- [ ] Zod スキーマ（`repositorySchema`・`branchSchema`・`treeItemSchema`・`fileContentSchema`）を `frontend/src/lib/api/schemas.ts` に追加する
- [ ] `frontend/src/lib/api/client.ts` に `listRepositories()`・`listBranches()`・`getRepositoryTree()`・`getFileContent()` を追加する

### フロントエンド UI
- [ ] `repo-store.svelte.ts` を作成する（接続中リポジトリ・選択ブランチを管理）
- [ ] `RepoPicker` コンポーネントを実装する（`frontend/src/lib/components/repo/repo-picker.svelte`）
  - リポジトリ一覧表示・テキスト検索・ページネーション
  - 0件時に「GitHub App をインストール」ボタンを表示
- [ ] `FileTree` コンポーネントを実装する（`frontend/src/lib/components/repo/file-tree.svelte`）
  - ディレクトリ折りたたみ、ファイルクリックで選択
- [ ] `FileViewer` コンポーネントを実装する（`frontend/src/lib/components/repo/file-viewer.svelte`）
  - テキストファイルをコードブロックで表示、非テキストはサイズのみ表示
- [ ] `[org]/+page.svelte` を更新する
  - 未接続: `RepoPicker` を表示
  - 接続済み: 左ペインに `FileTree`・右ペインに `FileViewer`・ブランチ切り替えセレクタ

## 完了条件

- `GET /api/v1/github/repositories` が認証済みユーザーにリポジトリ一覧を返すこと
- GitHub App 未インストール時に `reason: "app_not_installed"` を含む 404 が返ること
- リポジトリ一覧が表示され、検索で絞り込めること
- リポジトリを選択するとファイルツリーが左ペインに表示されること
- ファイルをクリックすると内容が右ペインに表示されること
- ブランチを切り替えるとツリーが更新されること

## 技術詳細

### API レスポンス形式

```json
// GET /api/v1/github/repositories
{ "repositories": [{ "owner": "org", "name": "repo", "full_name": "org/repo", "default_branch": "main", "private": false, "updated_at": "..." }], "page": 1, "has_more": false }

// GET /api/v1/github/repositories/{owner}/{repo}/tree
{ "tree": [{ "path": "src/index.ts", "type": "blob", "size": 1234 }], "branch": "main", "truncated": false }

// GET /api/v1/github/repositories/{owner}/{repo}/contents
{ "path": "src/index.ts", "content": "import ...", "sha": "abc123", "size": 1234 }
```

### 画面レイアウト（接続済み状態）

```
┌──────────────┬──────────────────────────┐
│ FileTree     │ FileViewer               │
│ ▼ src/       │ // src/index.ts          │
│   index.ts   │ import { ... }           │
│ ▶ tests/     │ ...                      │
└──────────────┴──────────────────────────┘
```

### ストア設計

```typescript
class RepoStore {
  connected = $state<RepositoryInfo | null>(null);
  selectedBranch = $state<string>("main");
  connect(repo: RepositoryInfo) { ... }
  disconnect() { ... }
}
```

### 参考実装

- `app_ref/ptw-respec/services/api/app/api/github.py`
- `app_ref/ptw-respec/services/api/app/services/github_git_client.py`
- `app_ref/ptw-respec/frontend/src/lib/components/RepoPicker.svelte`
