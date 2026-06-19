# GitHub App 統合基盤を実装する

## 概要

GitHub App の作成・設定、OAuth ログイン、インストールトークン管理サービス、Git クライアントを一括で実装し、Rosetta が GitHub リポジトリにアクセスできる基盤を整える。後続のリポジトリ一覧 API・ファイルツリー取得 API の前提となる。

## 背景・目的

Rosetta は GitHub リポジトリを対象にコード負債を検知する。そのためには GitHub App 経由でリポジトリを読み取る権限が必要で、開発者は GitHub アカウントでサインインして自分のリポジトリにアクセスできる必要がある。本 issue でその認証・アクセス基盤を一通り実装する。

## タスク

### 設定・環境
- [x] GitHub.com で Rosetta 用の GitHub App を作成する
- [x] `config.py` に GitHub App 用の設定項目を追加する（`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_SLUG`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `FRONTEND_ORIGIN`）
- [x] `.env.example` / `.env.dev` に変数を追加する
- [x] `pyproject.toml` に `PyJWT`・`cryptography`・`httpx`・`httpx-oauth` を追加する

### GitHub OAuth ログイン（バックエンド）
- [x] `OAuthAccount` モデルを作成する
- [x] `User` モデルに `oauth_accounts` リレーションを追加する
- [x] `oauth_accounts` テーブルのマイグレーションを作成する（`0002_add_oauth_accounts.py`）
- [x] `app/core/security.py` に GitHub OAuth クライアントを追加する（`RobustGitHubOAuth2`）
- [x] `app/api/v1/auth.py` に GitHub OAuth ルーターを追加する（`/api/v1/auth/github/authorize`・`/api/v1/auth/github/callback`）

### GitHub App サービス（バックエンド）
- [x] `backend/app/services/github_app.py` に `GitHubAppService` クラスを実装する
- [x] `backend/app/services/github_git_client.py` に `GitHubGitClient` クラスを実装する
- [x] DI ファクトリ関数 `get_github_app_service()` を `app/api/deps.py` に追加する

### GitHub OAuth ログイン（フロントエンド）
- [x] ログイン画面を作成する（「GitHub でサインイン」ボタン）
- [x] OAuth コールバックページ（`/login/callback`）を実装する
- [x] `auth.svelte.ts` ストアを実装する
- [x] `[org]/+layout.ts` に認証ガードを追加する

### テスト
- [x] `GitHubAppService` のユニットテストを書く（JWT 生成・トークンキャッシュ）
- [x] `GitHubGitClient.list_repositories()` のモックテストを書く

## 完了条件

- [x] 「GitHub でサインイン」ボタンをクリックすると GitHub の認可画面に遷移すること
- [x] 認可後にフロントエンドへリダイレクトされ、ログイン状態になること
- [x] `oauth_accounts` テーブルにレコードが作成されること
- [x] `GitHubAppService` のユニットテストが通ること（JWT 生成・トークンキャッシュ）
- [x] `GitHubGitClient.list_repositories()` がモックで正常に動作すること

## 技術詳細

### GitHub App 設定値

| 項目 | 値 |
|---|---|
| Callback URL | `http://localhost:8000/api/v1/auth/github/callback` と `http://localhost:5173/login/callback` |
| 権限: Contents | Read-only |
| 権限: Metadata | Read-only |
| 権限: Pull requests | Read-only |
| 権限: Email addresses | Read-only |

### OAuth コールバックのフロー（実装済み）

```
① ユーザーが「GitHub でサインイン」をクリック
② GET /api/v1/auth/github/authorize → { authorization_url } を返す
③ フロントエンドが window.location.href = authorization_url
④ GitHub の認可画面でユーザーが許可
⑤ GitHub → localhost:5173/login/callback?code=xxx&state=xxx
⑥ コールバックページが fetch('/api/v1/auth/github/callback?code=xxx&state=xxx')
⑦ バックエンドがトークン交換・ユーザー作成・Cookie セット（204）
⑧ auth.init() → listOrgs() → /{org_slug} にリダイレクト
```

### 参考実装

- `app_ref/ptw-respec/services/api/app/auth/router.py`
- `app_ref/ptw-respec/services/api/app/models/oauth_account.py`
- `app_ref/ptw-respec/services/api/app/services/github_app.py`
- `app_ref/ptw-respec/services/api/app/services/github_git_client.py`
