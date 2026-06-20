# TechStack 解析結果のテナント分離（クロステナント読み取りの是正）

## 概要 / 重大度

**重大度: High（クロステナント情報漏えい / IDOR）。**

`TechStack`（リポジトリのスタック解析結果）は `(owner, repo)` でグローバルに一意化され、
取得 API が org/project/installation のスコープ検証なしに `owner`/`repo` パスパラメータだけで
引ける。private リポジトリの解析結果を、別 org の認証ユーザ（または未認証）が読める。

## 該当箇所

- `backend/api/app/api/v1/stack.py:151-166`（GET `get_stack`）— **`current_active_user` 依存が無く**、
  `TechStack` を `owner`/`repo` だけで検索。
- `backend/api/app/api/v1/stack.py:111-143`（POST `analyze-stack`）— 認証 + `InstallationIdDep` はあるが、
  解決した installation が当該 `owner/repo` を参照できるか**検証していない**。任意 repo の解析を起動可。
- `backend/api/app/api/v1/jobs.py:24-44`（`_stack_tech_stack`、`:76` で使用）— 同じグローバルキャッシュを
  Job 経由で間接配信。

## 問題

スタック解析だけが他の解析ドメイン（031-036）と異なり project スコープに紐づいていないため、
`(owner, repo)` を知る/総当りする主体が他テナントの（private 含む）解析結果を取得できる。
GET には認証すら無い。

## 修正方針

1. スタック解析を **project スコープへ移設**: ルートを
   `/orgs/{slug}/projects/{project_slug}/...` 配下に置き、`OrgScope` で認可。
   `TechStack` 検索を `project.repo_owner`/`project.repo_name`（サーバ側値）で行い、`project_id` でも絞る。
   - 互換のため旧 `(owner, repo)` ルートは残すなら `current_active_user` + installation 可視性検証を必須化。
2. POST 起動時、解決した installation が `owner/repo` にアクセス可能か検証（不可なら 403/404）。
3. `jobs.get_job` のスタック投影も、Job の所有者（`created_by`）スコープ内に限定（現状の所有者スコープは
   維持しつつ、上記の project 紐付けで二重に保護）。

## 受け入れ条件

- 別 org のユーザが他 project の `TechStack` を読めない（テスト: 403/404）。
- 未認証 GET が 401（テスト）。
- フロント `client.ts` のスタック取得/起動呼び出しを新パスに追随（`getStack`/`analyzeStack`）。
- `frontend` の `bun run check/lint/test:unit` 緑、backend gates 緑。

## 対象外

- スタック解析パイプライン本体（018）のロジック変更。
