# プロジェクト機能の基盤を構築する（Org 配下に「1 プロジェクト = 1 リポジトリ」を導入し、機能メニューをプロジェクト単位へスコープ）

## 概要

現在 Rosetta のルートはすべて **Org スコープ**（`/[org]/...`）で、Galaxy / Matrix / Quizzes / Agents /
Learning / Repos のどの機能も「org に直結」している。一方で接続中リポジトリは
`frontend/src/lib/stores/repo-store.svelte.ts` の**揮発的なインメモリ状態**でしかなく、DB に永続化された
リポジトリ／プロジェクトのエンティティは存在しない（リロードで接続が消える）。

本 issue では Org 配下に第一級の **Project** エンティティを導入する。運用上の不変条件は
**1 プロジェクト = 1 git リポジトリ**。プロジェクトを切り替えると、サイドバーの機能メニューが
**そのプロジェクト（= リポジトリ）の負債データを主語に切り替わる**。これにより
「いま自分がどのリポジトリの技術負債を観測・返済しているか」をプロダクトの主軸に据える。

本 issue は **プロジェクトの永続化・切り替え基盤・ルート再スコープ**が目的であり、各機能（Galaxy /
Matrix 等）の中身は作り直さない。具体的には次の 6 点を整備する。

1. **Project データモデル + マイグレーション**（backend） — org 配下、1 リポジトリ束縛、ソフト削除
2. **Project CRUD API**（backend） — 既存 `OrgScope` 配下に `/orgs/{slug}/projects` 系
3. **project-store + API クライアント + Zod スキーマ**（frontend） — 現在プロジェクト / 一覧 / 最近開いた順
4. **プロジェクトスイッチャー**（frontend） — サイドバー上部の文脈切替 UI（GitLab context switcher の写像、ただし独自化）
5. **プロジェクト作成フロー**（frontend） — `RepoPicker` を再利用し、選んだリポジトリにプロジェクトを束縛
6. **ルート再スコープ**（frontend） — 既存機能ルートを `/[org]/[project]/...` 配下へ移設し、nav / breadcrumbs を project 化

## 背景・目的

### 現状（org スコープのみ・リポジトリは揮発）

- ルートは `[org]/+layout.svelte`（アプリシェル）配下に `galaxy` / `matrix` / `quizzes` / `agents` /
  `learning` / `repos` / `settings` がフラットに並ぶ（issue-005 で構築）。すべて org 直下で、
  リポジトリの概念がルートに現れない。
- リポジトリ接続は `repo-store.svelte.ts`（`connected: Repository | null` と `selectedBranch`）の
  **インメモリ state のみ**。`backend/app/api/v1/github.py` は GitHub App 経由でリポジトリ一覧・ツリー・
  ファイル内容を返すが、**どのリポジトリを「このユーザー / org が管理対象にしているか」を保存していない**。
- バックエンドの永続エンティティは `Org` / `OrgMember` / `User` / `OAuthAccount` / `RefreshToken` /
  `tech_stack` のみで、**Project / Repository テーブルは無い**。
- 仕様書 §7.1 のデータモデルでは `File.repo: string` / `CodeDebt.file_id` 等が**リポジトリを文字列として暗黙に
  参照**しており、リポジトリを束ねる第一級の置き場が無い。マルチリポジトリは §10.2 で Future 扱い。

### 目的

1. **リポジトリ束縛を永続化する**。揮発的な `repo-store` を、DB に保存された Project に置き換え、
   リロード・別デバイス・別メンバーでも「この org が観測対象にしているリポジトリ」が共有される状態にする。
2. **機能メニューをプロジェクト単位にスコープする**。Galaxy / Matrix / Quizzes / Agents / Learning /
   Repos を「org の機能」から「**選択中プロジェクトの機能**」へ格上げし、プロジェクト切り替えで
   メニューの主語（観測対象リポジトリ）が丸ごと切り替わるようにする。
3. **将来のマルチリポジトリ（§10.2 Future）への布石**を、データモデルとルート構造のレベルで先に打つ。
   Project を `File.repo` 等の正規の住所として確立し、1 org に複数 Project がぶら下がる構造を用意する。
4. **概念の整理**：Org = チーム / 課金 / メンバーシップの境界（既存・不変）、Project = 観測対象リポジトリの単位
   （新設）、という 2 層構造を明確にする。

### GitLab の丸パクリにしない（独自性の角度）

GitLab のスーパーサイドバーは **context switcher**（`organization_switcher.vue` / `sidebar_menu.vue`）で
group ↔ project ↔ Your work を切り替え、`lib/sidebars/projects/super_sidebar_panel.rb` が project context を
受け取ってメニューを宣言的に組み立てる。さらに `super_sidebar/utils.js` + `visitable.rb` で **frecency**
（頻度 × 直近性のスコアリング）により「最近よく開く project」を上位に出す。この**構造**は優れているので学ぶが、
Rosetta は次の点で意図的にずらす。

- **切り替えの主語を「観測対象リポジトリ」に再定義**する。GitLab の context switcher は group / project /
  organization という**所有・権限の階層**を渡り歩く道具だが、Rosetta のスイッチャーは
  「**いまどのリポジトリの技術負債を観測しているか**」を切り替える**天体望遠鏡の対象選択**である。
  各プロジェクト行には open 件数ではなく **KC% / 未返済負債残高**の双対指標（地層アンバー × 星ティール）を出す。
- **frecency は「最近観測した順」に軽量化**する。GitLab のような月次パーティションテーブル + 週次 dense_rank の
  サーバ側スコアリングは MVP では過剰。Rosetta は **localStorage に org 別「最近開いたプロジェクト」**を
  保持する軽量版（直近性のみ）に留める（サーバ側 frecency 集計は本 issue のスコープ外）。
- **配色・タイポは Pajamas を採らない**。issue-005 で確立した Twin パレット（アンバー = コード負債 / 地層、
  ティール = ナレッジ負債 / 星）+ Fraunces + near-black を踏襲し、スイッチャーも Rosetta の世界観で塗る。
- **パンくず（理解の階層）を Org > Project > 機能に拡張**する。GitLab のように group/project/path という
  リポジトリ構造を主語にせず、「Org（チーム）> 観測対象プロジェクト > 理解の区分」で表現する。

構造（宣言的メニュー組み立て・文脈ヘッダ・最近項目）は GitLab から学び、情報設計と世界観は Rosetta 独自にする。

## スコープ（in / out）

**含む（in）**

- Project の永続化（モデル + マイグレーション + CRUD API）
- プロジェクトスイッチャー UI（現在プロジェクト表示 + 一覧 + 検索 + 最近開いた順 + 新規作成導線）
- プロジェクト作成フロー（`RepoPicker` 再利用 → リポジトリ束縛）
- 既存機能ルートの `/[org]/[project]/...` への再スコープ（**機能本体のロジックは変更しない**）
- nav.ts / breadcrumbs / sidebar の project 化、Org ホーム（プロジェクト一覧）と空状態

**含まない（out / Future）**

- サーバ側 frecency 集計（訪問テーブル・週次スコア）。localStorage の「最近開いた順」で代替
- 1 プロジェクトに**複数**リポジトリの束縛（§10.2 マルチリポジトリ）。本 issue は 1:1 固定
- プロジェクト単位の権限（org メンバーシップを継承。プロジェクト個別 ACL は将来）
- 各機能（Galaxy / Matrix 等）のデータ取得を project_id で本当にフィルタする実装
  （**ルートとコンテキストの配線まで**。実データの project スコープ化は各機能 issue で対応）
- Webhook / 定期スキャンのプロジェクト紐付け

## タスク

### バックエンド: Project モデル + マイグレーション（`backend/app/models/project.py`）

- [ ] `Project(SQLModel, table=True)` を新設する（`Org` モデルの規約に倣う）
  - `id`（`uuid7_pk()`）/ `org_id`（FK `orgs.id`, indexed, not null）
  - `name`（表示名）/ `slug`（URL-safe, org 内で一意）
  - `repo_owner` / `repo_name` / `repo_full_name`（`owner/name`）/ `default_branch` / `repo_private`
  - `github_repo_id: int | None`（GitHub のリポジトリ安定 ID。リネーム耐性のため保持）
  - `created_by`（FK `users.id`）/ `created_at` / `updated_at` / `deleted_at`（ソフト削除）
- [ ] `backend/app/models/__init__.py` に `Project` を登録する
- [ ] Alembic マイグレーションを生成し、部分ユニーク制約を 2 本張る
  - `uq_projects_org_slug_active`: `(org_id, slug)` where `deleted_at IS NULL`（org 内 slug 一意）
  - `uq_projects_org_repo_active`: `(org_id, repo_full_name)` where `deleted_at IS NULL`（**1 リポジトリ = 1 プロジェクト**を DB で担保）

### バックエンド: Project API（`backend/app/api/v1/projects.py` + service）

- [ ] `backend/app/schemas/project.py` に `ProjectCreate` / `ProjectRead` / `ProjectUpdate` を定義する
- [ ] `backend/app/services/project.py` に `ProjectService` + `ProjectServiceDep` を実装する（`OrgService` に倣う）
  - slug 自動生成（name から kebab-case）+ **予約 slug 拒否**（`settings` / `new` 等、§技術詳細の予約語表）
  - 作成時に GitHub App 経由でリポジトリ実在・アクセス可否を検証（`github.py` の `resolve_github_client` を流用）
- [ ] 既存 `OrgScope`（`app/api/deps.py`）配下にルートを追加し、`router.py` に `projects_router` を登録する
  - [ ] `GET  /api/v1/orgs/{slug}/projects` — org のアクティブプロジェクト一覧（メンバー閲覧可）
  - [ ] `POST /api/v1/orgs/{slug}/projects` — 作成（`name` + `repo_full_name` / `owner` / `name` / `default_branch`）。要 ADMIN 以上
  - [ ] `GET  /api/v1/orgs/{slug}/projects/{project_slug}` — 単一取得
  - [ ] `PATCH /api/v1/orgs/{slug}/projects/{project_slug}` — 部分更新（`name` / `slug` / `default_branch`）。要 ADMIN 以上
  - [ ] `DELETE /api/v1/orgs/{slug}/projects/{project_slug}` — ソフト削除。要 ADMIN 以上
- [ ] pytest を追加（作成 / 一覧 / 重複 slug 拒否 / 重複リポジトリ拒否 / 予約 slug 拒否 / 権限境界 / ソフト削除）

### フロントエンド: API クライアント + Zod スキーマ

- [ ] `frontend/src/lib/api/schemas.ts` に `projectSchema` / `projectCreateSchema` / `Project` 型を追加する
      （`orgSchema` / `repositorySchema` の規約に倣い snake_case のまま）
- [ ] `frontend/src/lib/api/client.ts` に `listProjects(orgSlug)` / `createProject(orgSlug, body)` /
      `getProject(orgSlug, projectSlug)` / `patchProject(...)` / `deleteProject(...)` を追加する

### フロントエンド: project-store（`frontend/src/lib/stores/project-store.svelte.ts`）

- [ ] Svelte 5 クラスベース runes で `ProjectStore` を実装する
  - `current = $state<Project | null>(null)`（`[org]/[project]/+layout.ts` で解決してセット）
  - `list = $state<Project[]>([])`（スイッチャー用。org 切替時にロード）
  - `recentIds`（org 別の「最近開いたプロジェクト」ID 配列。`localStorage` に永続化、直近性のみの frecency-lite）
  - `touch(orgSlug, projectId)` / `setCurrent(p)` / `loadList(orgSlug)` を提供
- [ ] **既存 `repo-store` を整理**する：束縛リポジトリの正は Project（`current.repo_*`）に一本化し、
      `repo-store` は「ファイルビューア用の選択ブランチ」だけ残す（または project-store に統合）。
      `repo.connected` を参照していた箇所（`super-sidebar.svelte` / `breadcrumbs.svelte` の `repoConnected`）を
      `project.current !== null` ベースに置換する

### フロントエンド: プロジェクトスイッチャー（`frontend/src/lib/components/shell/`）

- [ ] `project-switcher.svelte` — サイドバー最上部の文脈切替（GitLab `organization_switcher.vue` の写像）
  - 現在プロジェクト表示：リポジトリアイコン + プロジェクト名 + `repo_full_name` 小字 + 開閉シェブロン
  - 未選択時（`/[org]` 上）は「プロジェクトを選択」プレースホルダ表示
  - クリックで `dropdown-menu`（または `popover`）を開く：
    - **検索ボックス**（名前 / `repo_full_name` で前方一致フィルタ）
    - **最近開いた**セクション（`project.recentIds` 順、上位 5 件）
    - **すべてのプロジェクト**セクション（各行に名前 + repo + KC% / 負債 pill のダミー値）
    - フッターに **「+ 新規プロジェクト」** CTA
  - 折りたたみ（`sidebar.collapsed`）時はアイコンのみ + tooltip
- [ ] `super-sidebar.svelte` の最上部（ピン留めセクションより上）に `project-switcher` を差し込む

### フロントエンド: プロジェクト作成フロー

- [ ] `frontend/src/routes/[org]/projects/new/+page.svelte` を新設する（または既存 `RepoPicker` を内包するダイアログ）
  - 既存 `frontend/src/lib/components/repo/repo-picker.svelte` を再利用してリポジトリを選択
  - リポジトリ選択 → プロジェクト名（デフォルトは repo 名）→ `createProject` 呼び出し
  - 成功時に `/[org]/[project]` へ遷移し、`project-store` に反映
  - 0 件時（GitHub App 未インストール）は既存の導線（インストールボタン）をそのまま活かす

### フロントエンド: ルート再スコープ（`/[org]/[project]/...`）

- [ ] `frontend/src/routes/[org]/[project]/+layout.ts` を新設する
  - `params.project` を `getProject(orgSlug, projectSlug)` で解決し、無ければ `error(404)`
  - 解決した Project を `project-store.current` にセットし、`touch()` で最近開いた順を更新
- [ ] 既存の機能ルートを **`[org]/` から `[org]/[project]/` 配下へ移設**する（§技術詳細の移行表）
  - `galaxy` / `matrix`（+ `[debtId]`）/ `quizzes`（+ `[sessionId]` + `result`）/ `agents` / `learning` / `repos`
  - 各 `+page.ts` ローダの相対 import / `$types` 参照を新パスへ追従させる
  - **機能本体のロジックは変更しない**（ルート位置と project コンテキストの受け取りのみ）
- [ ] `[org]/+page.svelte`（現 Overview）を **Org ホーム = プロジェクト一覧**に作り替える
  - プロジェクトカード一覧（名前 + repo + KC / 負債ダミー pill）+ 「新規プロジェクト」CTA
  - 0 件時は共通 `empty-state` で「最初のプロジェクトを作成」を表示
- [ ] `[org]/[project]/+page.svelte` を **プロジェクト概要**にする（旧 Overview ダッシュボードの placeholder をこちらへ）

### フロントエンド: nav / breadcrumbs / settings の project 化

- [ ] `frontend/src/lib/config/nav.ts` の `NavContext` に `projectSlug: string` を追加し、
      各 `route` を `(c) => `/${c.orgSlug}/${c.projectSlug}/...`` に変更する
  - Overview は `/[org]/[project]`、Galaxy 等は `/[org]/[project]/galaxy` …
  - `pill` 取得関数を project スコープ前提に読み替える（本 issue ではダミー固定で可）
- [ ] `super-sidebar.svelte` / `menu-section.svelte` / `nav-item.svelte` の `ctx` 生成に `projectSlug` を渡す
  - **プロジェクト未選択（`/[org]`）では機能セクションを非表示 / 不活性**にし、スイッチャーと Org ホームへ誘導
- [ ] `breadcrumbs.svelte` を **Org > Project > 機能**に拡張する（現状 Org > 機能）
- [ ] **org settings と project settings を分離**する
  - org settings は `[org]/settings`（既存・issue-013 のメンバー管理を含む）に据え置き
  - project settings は `[org]/[project]/settings`（リネーム / 既定ブランチ変更 / リポジトリ束縛確認 / プロジェクト削除）を新設
  - nav の Settings 項目は文脈に応じて出し分ける（プロジェクト内では project settings、Org ホームでは org settings）

### i18n（Paraglide 2.0）

- [ ] `frontend/messages/ja.json` / `en.json` にラベルを追加する（既存 `nav_*` の snake_case 命名に倣う）
  - `project_switcher_current` / `project_switcher_select` / `project_switcher_recent` /
    `project_switcher_all` / `project_switcher_search_placeholder` / `project_create_cta` /
    `project_create_title` / `project_create_name_label` / `project_empty_title` / `project_empty_desc` 等

## 完了条件

- Org 配下に Project が**永続化**され、リロード後も org の観測対象リポジトリ（= プロジェクト一覧）が保持されること
- `POST /api/v1/orgs/{slug}/projects` で**実在しない / アクセス不可のリポジトリは拒否**され、
  同一 org 内の**重複 slug・重複リポジトリ束縛・予約 slug が 4xx で拒否**されること
- サイドバー上部のスイッチャーで現在プロジェクトが表示され、**一覧から別プロジェクトに切り替えると
  機能メニューの主語（観測対象リポジトリ）が切り替わる**こと
- スイッチャーの検索でプロジェクトを絞り込め、**最近開いた順**が localStorage で保持されること
- `/[org]/[project]/{galaxy,matrix,quizzes,agents,learning,repos}` の各ルートが従来どおり描画されること
  （機能本体の挙動が回帰しないこと）
- `/[org]` がプロジェクト一覧（0 件時は空状態 + 作成 CTA）になり、`/[org]/[project]` がプロジェクト概要になること
- パンくずが **Org > Project > 機能**で表示されること
- 存在しない project slug で `/[org]/{unknown}` にアクセスすると 404 になること
- org settings（`/[org]/settings`、メンバー管理）と project settings（`/[org]/[project]/settings`）が分離されていること
- `cd backend && uv run ruff check app/ && uv run ruff format --check app/ && uv run ty check` と
  `uv run pytest` がパスすること
- `cd frontend && bun run check` / `bun run lint` がパスすること

## 技術詳細

### 概念モデル（2 層）

```
Org（チーム / 課金 / メンバーシップの境界 — 既存・不変）
└── Project（観測対象 = 1 git リポジトリ — 新設）   ※ 1 org : N projects
    └── 機能データ: Code/Knowledge Debt, Galaxy, Quiz, LearningPlan …（project_id でスコープ）
```

仕様書 §7.1 の `File.repo: string` / `CodeDebt.file_id` 等が暗黙参照していた「リポジトリ」を、
Project として第一級化する。Project = `File.repo` の正規の住所。

### データモデル（`Project`）

```python
# backend/app/models/project.py — Org モデル(app/models/org.py)の規約に倣う
class Project(SQLModel, table=True):
    """An observed git repository within an org. 1 project == 1 repository.

    Soft-deleted via `deleted_at`. Partial unique indexes (in the Alembic migration)
    enforce slug uniqueness and one-repo-per-project among non-deleted rows, scoped to org.
    """

    __tablename__ = "projects"

    id: uuid.UUID = uuid7_pk()
    org_id: uuid.UUID = Field(foreign_key="orgs.id", nullable=False, index=True)
    name: str = Field(nullable=False, description="Human-readable project name.")
    slug: str = Field(nullable=False, description="URL-safe id, unique within the org.")
    repo_owner: str = Field(nullable=False)
    repo_name: str = Field(nullable=False)
    repo_full_name: str = Field(nullable=False, description="owner/name")
    default_branch: str = Field(nullable=False, default="main")
    repo_private: bool = Field(default=False, nullable=False)
    github_repo_id: int | None = Field(default=None, description="Stable GitHub repo id (rename-resilient).")
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    deleted_at: datetime | None = deleted_at_field()
```

マイグレーションで張る部分ユニーク制約（`Org` の `uq_orgs_slug_active` に倣う）:

```sql
CREATE UNIQUE INDEX uq_projects_org_slug_active ON projects (org_id, slug)      WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_projects_org_repo_active ON projects (org_id, repo_full_name) WHERE deleted_at IS NULL;
```

### ルーティング設計（`[org]/[project]/...`）

SvelteKit は**静的ルートを動的ルートより優先**する。よって `[org]/settings`（org 設定・静的）は
`[org]/[project]`（動的）より先にマッチし共存できる。ただしプロジェクト slug がこれらを侵食しないよう、
**作成時に予約 slug を拒否**する。

予約 slug（`[org]/` 直下の静的セグメント）: `settings` / `projects` / `new` / `members` / `-`（将来分も含め拒否）

```
┌──────────────────────────────────────────────────────────────────────┐
│ Topbar:  [▤] [Λ Rosetta]   Org > Project > Matrix      [⌘K] [◍]       │
├──────────────┬───────────────────────────────────────────────────────┤
│ ▼ Project ▾  │   ← プロジェクトスイッチャー（文脈ヘッダ）              │
│   acme/web   │                                                       │
│ ─ ピン留め   │   Content（/[org]/[project]/* の各 +page.svelte）      │
│ ─ UNDERSTAND │                                                       │
│   ◎ Overview │                                                       │
│   ✦ Galaxy 62%                                                       │
│   ▦ Matrix  8                                                        │
│   ? Quizzes 3                                                        │
│   ⚙ Agents                                                          │
│   ↑ Learning                                                        │
│ ─ REFERENCE  │                                                       │
│   ▤ Repos    │                                                       │
└──────────────┴───────────────────────────────────────────────────────┘
```

### ルート移行表（現行 → 変更後）

| 機能 | 現行 | 変更後 |
|---|---|---|
| Org ホーム | `[org]/+page.svelte`（Overview placeholder） | `[org]/+page.svelte`（**プロジェクト一覧** + 作成 CTA） |
| プロジェクト概要 | （無し） | `[org]/[project]/+page.svelte`（旧 Overview をこちらへ） |
| Galaxy | `[org]/galaxy` | `[org]/[project]/galaxy` |
| Matrix | `[org]/matrix` / `[org]/matrix/[debtId]` | `[org]/[project]/matrix` / `.../[debtId]` |
| Quizzes | `[org]/quizzes` / `.../[sessionId]` / `.../result` | `[org]/[project]/quizzes/...` |
| Agents | `[org]/agents` | `[org]/[project]/agents` |
| Learning | `[org]/learning` | `[org]/[project]/learning` |
| Repos | `[org]/repos`（RepoPicker） | `[org]/[project]/repos`（束縛リポジトリのファイルビューア）。Picker は作成フローへ移動 |
| org 設定 | `[org]/settings` | `[org]/settings`（据え置き・メンバー管理） |
| project 設定 | （無し） | `[org]/[project]/settings`（リネーム / 既定ブランチ / 削除） |

アプリシェル（`[org]/+layout.svelte` の topbar + sidebar）は据え置き。project コンテキストは
`page.params.project` と `project-store.current` から読む。`[org]/[project]/+layout.ts` で project を解決する。

### API 仕様（既存 `OrgScope` 配下）

```jsonc
// POST /api/v1/orgs/{slug}/projects  (要 ADMIN 以上)
// req
{ "name": "Web フロントエンド", "repo_full_name": "acme/web", "default_branch": "main" }
// res 201
{ "id": "01...", "org_id": "01...", "name": "Web フロントエンド", "slug": "web-frontend",
  "repo_owner": "acme", "repo_name": "web", "repo_full_name": "acme/web",
  "default_branch": "main", "repo_private": true, "github_repo_id": 123456,
  "created_at": "...", "updated_at": "..." }

// GET /api/v1/orgs/{slug}/projects  → { "projects": [ProjectRead, ...] }
// 重複 slug / 重複リポジトリ / 予約 slug → 409 or 422
```

作成時は `github.py` の `resolve_github_client` を流用し、`repo_full_name` が GitHub App インストールから
到達可能かを検証してから INSERT する（到達不可なら 404 `app_not_installed` / 422）。

### project-store（`frontend/src/lib/stores/project-store.svelte.ts`）

```typescript
import type { Project } from "$lib/api/schemas";

class ProjectStore {
  current = $state<Project | null>(null);
  list = $state<Project[]>([]);
  // org 別「最近開いた順」プロジェクト ID（直近性のみの frecency-lite）
  recentByOrg = $state<Record<string, string[]>>({});

  constructor() {
    if (typeof localStorage !== "undefined") {
      this.recentByOrg = JSON.parse(localStorage.getItem("rosetta:project:recent") ?? "{}");
    }
  }
  setCurrent(p: Project | null) { this.current = p; }
  touch(orgSlug: string, projectId: string) {
    const prev = (this.recentByOrg[orgSlug] ?? []).filter((id) => id !== projectId);
    this.recentByOrg = { ...this.recentByOrg, [orgSlug]: [projectId, ...prev].slice(0, 10) };
    localStorage.setItem("rosetta:project:recent", JSON.stringify(this.recentByOrg));
  }
}
export const project = new ProjectStore();
```

> GitLab の `super_sidebar/utils.js` + `visitable.rb` はサーバ側 frecency（週次 dense_rank）で「よく開く project」を
> 出すが、Rosetta は MVP では **localStorage の最近開いた順**に留める（サーバ側集計は Future）。

### NavContext の変更（`nav.ts`）

```typescript
// Before: { orgSlug, repoConnected }
export type NavContext = { orgSlug: string; projectSlug: string; projectSelected: boolean };

// route は project 相対へ
{ id: "galaxy", label: m.nav_galaxy, icon: Sparkles,
  route: (c) => `/${c.orgSlug}/${c.projectSlug}/galaxy`, pill: () => (galaxy.myKc !== null ? `${galaxy.myKc}%` : null) }
```

`super-sidebar.svelte` の `ctx` 生成を `{ orgSlug: page.params.org, projectSlug: page.params.project ?? "",
projectSelected: project.current !== null }` に置換し、`projectSelected === false`（= `/[org]` 上）では
機能セクションを描画しない（スイッチャーと Org ホームのみ）。

### プロジェクトスイッチャー UI（GitLab 写像）

GitLab の `organization_switcher.vue`（`GlDisclosureDropdown` で現在文脈 + 切替候補 + フッタを出す）を、
shadcn `dropdown-menu` / `popover` + `command`（検索付き）で写像する。

```
┌─ project-switcher（開いた状態）──────────┐
│ [🔍 プロジェクトを検索...            ]    │
│ 最近開いた                                │
│   ▣ acme/web        KC 62% · 負債 8       │
│   ▣ acme/api        KC 41% · 負債 14      │
│ すべてのプロジェクト                      │
│   ▣ acme/mobile     KC 55% · 負債 5       │
│   ▣ acme/infra      KC 30% · 負債 21      │
│ ─────────────────────────────────────    │
│ + 新規プロジェクト                        │
└───────────────────────────────────────────┘
```

各行の `KC% · 負債` は Twin 双対指標（ティール KC / アンバー負債）。本 issue ではダミー固定で可。

### 段階的移行メモ

ルート再スコープは機械的移動 + コンテキスト配線が中心で本体ロジックを変えないが、影響範囲が広い。
レビュー容易性のため、PR を「(1) backend モデル + API + テスト」「(2) frontend store + スイッチャー + 作成フロー」
「(3) ルート移設 + nav/breadcrumbs/settings 配線」の 3 コミットに分けることを推奨する（issue は 1 本）。

## 参考

- 仕様書 `仕様書.md`
  - §7.1 主要エンティティ（`File.repo` / `CodeDebt` 等が暗黙参照するリポジトリを Project として第一級化）
  - §2.3 二軸負債モデル（プロジェクト行に出す KC% / 負債残高の意味づけ）
  - §6.1 ダッシュボード（プロジェクト概要の将来仕様）
  - §10.2 MVP に含まないもの（マルチリポジトリ = Future。本 issue は 1 プロジェクト : 1 リポジトリ固定でその布石）
- GitLab 参考実装（`gitlab/`）— 構造を学び、世界観は独自化する
  - `app/assets/javascripts/super_sidebar/components/organization_switcher.vue`（文脈切替ドロップダウン = スイッチャーの写像元）
  - `app/assets/javascripts/super_sidebar/components/sidebar_menu.vue`（文脈に応じたメニュー描画）
  - `app/assets/javascripts/super_sidebar/utils.js`（`trackContextAccess` — 最近項目の localStorage 追跡。Rosetta は軽量版）
  - `app/models/concerns/users/visitable.rb` / `app/models/users/project_visit.rb`（サーバ側 frecency — 本 issue では非採用、Future 参考）
  - `lib/sidebars/projects/super_sidebar_panel.rb` / `lib/sidebars/context.rb`（project context を受けたメニュー宣言的組み立て）
  - `app/helpers/sidebars_helper.rb`（`super_sidebar_current_context` — 現在文脈のデータ形 `{namespace, item:{...}}`）
- 現行コード
  - `frontend/src/routes/[org]/+layout.svelte`（アプリシェル — 据え置き、project コンテキストを読む）
  - `frontend/src/routes/[org]/+page.svelte` ほか各機能ルート（`[org]/[project]/` 配下へ移設）
  - `frontend/src/lib/config/nav.ts`（`NavContext` に `projectSlug` 追加、route を project 相対へ）
  - `frontend/src/lib/components/shell/{super-sidebar,breadcrumbs,menu-section,nav-item}.svelte`（project 化）
  - `frontend/src/lib/stores/repo-store.svelte.ts`（Project へ一本化、ブランチ選択のみ残す）
  - `frontend/src/lib/components/repo/repo-picker.svelte`（作成フローで再利用）
  - `backend/app/models/org.py`（`Project` モデルの規約モデル）
  - `backend/app/api/v1/orgs.py` / `app/api/deps.py`（`OrgScope` / `OrgAdminScope` を `projects` でも流用）
  - `backend/app/api/v1/github.py`（`resolve_github_client` を作成時のリポジトリ検証に流用）
  - `backend/app/api/v1/router.py`（`projects_router` を登録）
- 関連 Issue: issue-002（リポジトリ接続・ビューア / RepoPicker）、issue-005（アプリシェル・スーパーサイドバー基盤）、
  issue-013（org メンバー管理 — org settings と project settings の分離の前提）
```
