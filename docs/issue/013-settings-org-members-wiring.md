# Settings: org メンバー管理 UI を配線する（既存 API の UI 未配線を解消）

## 概要

`frontend/src/lib/api/client.ts` には `listMembers` / `inviteMember` /
`patchMemberRole` / `removeMember` / `getMyMembership` が**既に実装済み**だが、
これらを呼び出す画面が存在しない（API 先行・UI 未配線）状態にある。
本 issue では `[org]/settings/members` ルートを **Settings セクションの末尾固定**で新設し、
(1) メンバー一覧（アバター + email + ロールバッジ）、(2) 招待（email 入力）、
(3) ロール変更（owner / admin / member の PATCH）、(4) 削除 を UI として配線する。

GitLab の Members（`project_information_menu.rb` の Manage グルーピング配下）の
情報設計（IA）を踏襲しつつ、メンバー行に **その人の org KC 寄与のミニ指標枠** を
仕込み、後続の Knowledge Galaxy / 二軸負債マトリクスと **KC を共通言語** で繋ぐ布石とする。

## 背景・目的

### 現状（API 先行・UI 未配線）

バックエンドの org メンバー API（`/api/v1/orgs/{slug}/members` 系）と、それを叩く
フロント関数は `frontend/src/lib/api/client.ts` 内に既に揃っている：

| 関数 | メソッド / パス | 戻り値 |
|---|---|---|
| `getMyMembership(orgSlug)` | `GET /api/v1/orgs/{slug}/me` | `OrgMember \| null` |
| `listMembers(orgSlug)` | `GET /api/v1/orgs/{slug}/members` | `OrgMember[]` |
| `inviteMember(orgSlug, email)` | `POST /api/v1/orgs/{slug}/members` | `OrgMember` |
| `patchMemberRole(orgSlug, userId, role)` | `PATCH /api/v1/orgs/{slug}/members/{userId}` | `OrgMember` |
| `removeMember(orgSlug, userId)` | `DELETE /api/v1/orgs/{slug}/members/{userId}` | `void` |

しかし `frontend/src/routes/` 配下に `settings/` ルートは存在せず
（現状 `[org]/+page.svelte` はリポジトリビューアのみ）、これらの関数を呼ぶ導線が無い。
結果として「招待・ロール変更・退会」がプロダクトとして成立していない。

### 目的

1. 既存 API を素直に配線し、**メンバー管理を機能として閉じる**。
2. GitLab の枯れた Members IA（Manage グルーピング・末尾固定）を採用し、
   ナビ構造を学習コストの低いものにする。
3. Rosetta の一級概念である **Knowledge Coverage (KC)** を Settings にも通底させ、
   「メンバー = KC の寄与主体」という見方をこの画面の段階から刷り込む。

### 前提 Issue（depends_on）

- **`app-shell-super-sidebar-foundation`**（Super Sidebar 基盤）。
  本 issue の「Settings セクション末尾固定」は、Super Sidebar の領域グルーピング
  （understand 系動詞 → … → 末尾 Settings）が存在することを前提とする。
  基盤が未マージの場合は `[org]/+layout.svelte` のヘッダ内に暫定リンクを置いて先行配線し、
  サイドバー確定後に正式枠へ移設してよい。

### 独自性（GitLab の丸パクリにしない）

GitLab の Members 一覧は「アバター + ロール + 有効期限 + アクション」を並べる
純粋な権限管理テーブルである。Rosetta はここで一歩踏み込み、各メンバー行に
**org KC 寄与のミニ指標枠**（仕様書 §5.1 の `KC(file, dev)` を開発者軸に集約した値）を
差し込む。これは GitLab には存在しない列であり、「このメンバーは org の知識被覆に
どれだけ貢献しているか」を権限管理と同じ場所で一目で見せる。

ただし本 issue 時点では KC 集約 API はまだ無いため、ミニ指標枠は
**プレースホルダ（`—` 表示 + ツールチップで Coming Soon を明示）** として枠だけ用意し、
後続 issue で `GET /api/v1/orgs/{slug}/members/{userId}/kc` を繋ぐ。
理解度を一級市民として扱う Rosetta の思想を、権限画面にも布石として埋め込む狙いである。
なお IA 規律として **Settings は末尾固定**（understand 系動詞より下）に置く点は崩さない。

## タスク

### ナビゲーション（Settings セクション末尾固定）

- [ ] Super Sidebar の **Settings セクション末尾** に「Members」項目を追加する
      （GitLab の `UncategorizedMenu` を Settings 直前に差し込む末尾固定パターンに倣い、
      Settings グループ自体を最下段に固定）
- [ ] リンク先を `[org]/settings/members` とし、`active_routes` 相当のアクティブ判定を
      現在パス（`page.url.pathname`）一致で実装する
- [ ] 前提 Issue 未マージ時の暫定導線として `[org]/+layout.svelte` ヘッダに
      設定リンクを置く（基盤確定後に削除）

### ルート / ページ（`frontend/src/routes/[org]/settings/`）

- [ ] `[org]/settings/+layout.svelte` を新設する（Settings 共通の見出し + サブナビ枠）
- [ ] `[org]/settings/members/+page.svelte` を新設する（メンバー管理本体）
- [ ] `[org]/settings/members/+page.ts` で `load` 時に `getMyMembership(orgSlug)` を取得し、
      `myRole` をページデータとして渡す（権限ガードの初期値）

### ストア（`frontend/src/lib/stores/`）

- [ ] `members-store.svelte.ts` を新設する（Svelte 5 クラスベース runes）
  - `members = $state<OrgMember[]>([])` / `loading` / `myRole`
  - `load(orgSlug)` / `invite(orgSlug, email)` / `changeRole(orgSlug, userId, role)` /
    `remove(orgSlug, userId)` を実装し、楽観更新後に確定値で差し替え
  - `canManage = $derived(this.myRole === "owner" || this.myRole === "admin")`

### コンポーネント（`frontend/src/lib/components/members/`）

- [ ] `member-list.svelte` — メンバー一覧（行レンダリング、空状態）
- [ ] `member-row.svelte` — 1 行（アバター + display_name/email + ロールバッジ +
      KC 寄与ミニ指標枠 + アクション）
- [ ] `member-role-badge.svelte` — owner / admin / member のロールバッジ（色分け）
- [ ] `member-role-dropdown.svelte` — `dropdown-menu` でロール変更（`canManage` 時のみ）
- [ ] `invite-member-form.svelte` — email 入力 + 招待ボタン（`form-field` + zod 検証）
- [ ] `remove-member-dialog.svelte` — 削除確認 `dialog`
- [ ] `kc-contribution-cell.svelte` — KC 寄与ミニ指標枠（本 issue ではプレースホルダ）

### shadcn-svelte プリミティブ追加

- [ ] `avatar` を追加する（`bunx shadcn-svelte@latest add avatar`）
      — 現状 `frontend/src/lib/components/ui/` に未導入
- [ ] `badge` を追加する（`bunx shadcn-svelte@latest add badge`）— 同上
      （`dropdown-menu` / `dialog` / `input` / `form-field` / `tooltip` は導入済みを利用）

### スキーマ / クライアント（既存活用、差分のみ）

- [ ] `frontend/src/lib/api/schemas.ts` の `orgMemberSchema` / `orgRoleSchema` を再利用
      （**新規スキーマ追加は不要**。型はすべて既存）
- [ ] `client.ts` の関数群は**そのまま配線**（シグネチャ変更なし）

### i18n（Paraglide）

- [ ] `frontend/messages/ja.json` / `en.json` に members 画面の文言キーを追加
      （`members_title` / `members_invite` / `members_role_owner` 等、ja を主・en を従）

### 権限ガード

- [ ] `getMyMembership` の結果（`myRole`）で編集系 UI（ロール変更・削除・招待）を
      `canManage`（owner / admin）でのみ有効化、それ以外は閲覧専用にする
- [ ] 最後の owner を降格 / 削除できないガード（API 422 を受けてトースト表示）

### テスト

- [ ] `member-row.svelte.spec.ts`（browser-mode）— ロールバッジ表示・`canManage` による
      アクション出し分け
- [ ] `members-store` の `load` / `invite` / `changeRole` / `remove`（API モック）

## 完了条件

- Super Sidebar の **Settings セクション末尾** に Members 項目が表示され、
  クリックで `[org]/settings/members` に遷移すること（understand 系動詞より下に固定）
- メンバー一覧がアバター + 表示名 / email + ロールバッジで表示されること
- owner / admin（`canManage`）でログインした場合のみ、招待フォーム・ロール変更
  dropdown・削除ボタンが操作可能で、member ロールでは閲覧専用になること
- email を入力して招待すると一覧に新メンバーが追加されること（`POST /members`）
- ロール変更 dropdown で role を変えると `PATCH /members/{userId}` が走り、バッジが更新されること
- 削除確認 dialog で確定すると `DELETE /members/{userId}` が走り、行が消えること
- 各メンバー行に **KC 寄与ミニ指標枠** が存在し（本 issue ではプレースホルダ `—` +
  Coming Soon ツールチップ）、後続で実データを差し込める構造になっていること
- 最後の owner を降格 / 削除しようとした場合にエラートーストが出ること
- `bun run check` / `bun run lint` / `bun run test:unit` がパスすること

## 技術詳細

### 画面レイアウト

```
┌──────────────────────────────────────────────────────────────┐
│ Settings ▸ Members                          [+ メンバーを招待] │
├──────────────────────────────────────────────────────────────┤
│  招待  ┌──────────────────────────────┐                       │
│        │ email を入力…                 │  [招待する]            │
│        └──────────────────────────────┘                       │
├──────────────────────────────────────────────────────────────┤
│  メンバー (4)                                                  │
│ ┌────┬────────────────────┬──────────┬──────────┬──────────┐  │
│ │ AV │ name / email       │ KC 寄与  │ ロール   │ アクション│  │
│ ├────┼────────────────────┼──────────┼──────────┼──────────┤  │
│ │ ◍  │ Haruto             │  ▮▮▮▯ —   │ [owner ▾]│   ⋯      │  │
│ │    │ haruto@2wins.ai    │  (soon)  │          │          │  │
│ ├────┼────────────────────┼──────────┼──────────┼──────────┤  │
│ │ ◍  │ bob                │  ▮▯▯▯ —   │ [admin ▾]│  [削除]  │  │
│ │    │ bob@example.com    │  (soon)  │          │          │  │
│ └────┴────────────────────┴──────────┴──────────┴──────────┘  │
└──────────────────────────────────────────────────────────────┘
   ※ ロール変更 ▾ / 削除 は canManage（owner/admin）でのみ活性
   ※ KC 寄与列は枠のみ（プレースホルダ）。後続 issue で実データ配線
```

### コンポーネント構成

```
[org]/settings/+layout.svelte           ← Settings 共通シェル（見出し + サブナビ）
  └ [org]/settings/members/+page.svelte  ← メンバー管理本体
        ├ invite-member-form.svelte      ← email 入力 + 招待
        └ member-list.svelte             ← 一覧 + 空状態
              └ member-row.svelte        ← 1 行
                    ├ ui/avatar          ← shadcn avatar（要追加）
                    ├ member-role-badge.svelte    ← ui/badge ラップ（要追加）
                    ├ kc-contribution-cell.svelte ← KC 寄与（プレースホルダ）
                    ├ member-role-dropdown.svelte ← ui/dropdown-menu
                    └ remove-member-dialog.svelte ← ui/dialog

stores/members-store.svelte.ts           ← 一覧 / myRole / canManage / CRUD
```

> 注: `frontend/src/lib/components/ui/` は読み取り専用（shadcn プリミティブ）。
> カスタムは必ず `ui/` *外* のラッパー（`member-role-badge.svelte` 等）で `cn` 合成する。

### ストア設計

```typescript
// frontend/src/lib/stores/members-store.svelte.ts
import {
  listMembers,
  inviteMember,
  patchMemberRole,
  removeMember,
} from "$lib/api/client";
import type { OrgMember, OrgRole } from "$lib/api/schemas";

class MembersStore {
  members = $state<OrgMember[]>([]);
  myRole = $state<OrgRole | null>(null);
  loading = $state(false);

  canManage = $derived(this.myRole === "owner" || this.myRole === "admin");

  async load(orgSlug: string) {
    this.loading = true;
    try {
      this.members = await listMembers(orgSlug);
    } finally {
      this.loading = false;
    }
  }

  async invite(orgSlug: string, email: string) {
    const created = await inviteMember(orgSlug, email);
    this.members = [...this.members, created];
  }

  async changeRole(orgSlug: string, userId: string, role: OrgRole) {
    const updated = await patchMemberRole(orgSlug, userId, role);
    this.members = this.members.map((m) => (m.user_id === userId ? updated : m));
  }

  async remove(orgSlug: string, userId: string) {
    await removeMember(orgSlug, userId);
    this.members = this.members.filter((m) => m.user_id !== userId);
  }
}

export const members = new MembersStore();
```

### 型（既存 — 追加不要）

`frontend/src/lib/api/schemas.ts` に既に定義済みのものをそのまま使う：

```typescript
export const orgRoleSchema = z.enum(["owner", "admin", "member"]);

export const orgMemberSchema = z.object({
  id: z.uuid(),
  user_id: z.uuid(),
  org_id: z.uuid(),
  role: orgRoleSchema, // "owner" | "admin" | "member"
  created_at: z.iso.datetime({ offset: true }),
  user: orgMemberUserSchema, // { id, email, display_name, last_active_at?, is_active }
});

export type OrgRole = z.infer<typeof orgRoleSchema>;
export type OrgMember = z.infer<typeof orgMemberSchema>;
```

> snake_case フィールド（`user_id` / `display_name`）はそのまま保持する
> （camelCase 変換はリポジトリ全体でまだ導入していない）。

### ページ load と権限ガード

```typescript
// frontend/src/routes/[org]/settings/members/+page.ts
import { getMyMembership } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const load: PageLoad = async ({ params }) => {
  const me = await getMyMembership(params.org);
  return { orgSlug: params.org, myRole: me?.role ?? null };
};
```

```svelte
<!-- [org]/settings/members/+page.svelte（抜粋） -->
<script lang="ts">
  import { members } from "$lib/stores/members-store.svelte";
  import InviteMemberForm from "$lib/components/members/invite-member-form.svelte";
  import MemberList from "$lib/components/members/member-list.svelte";

  let { data } = $props();

  $effect(() => {
    members.myRole = data.myRole;
    members.load(data.orgSlug);
  });
</script>

{#if members.canManage}
  <InviteMemberForm orgSlug={data.orgSlug} />
{/if}
<MemberList orgSlug={data.orgSlug} />
```

### KC 寄与ミニ指標枠（プレースホルダ → 後続で実データ）

GitLab には無い Rosetta 独自列。本 issue では枠だけ用意し、Coming Soon を明示する。

```svelte
<!-- frontend/src/lib/components/members/kc-contribution-cell.svelte -->
<script lang="ts">
  import * as Tooltip from "$lib/components/ui/tooltip";
  // 後続 issue で member.kcContribution（0..1）を受け取り、
  // sparkline / 4 段階バーで描画する。今は枠のみ。
</script>

<Tooltip.Root>
  <Tooltip.Trigger>
    <span class="inline-flex items-center gap-1 text-muted-foreground">
      <span aria-hidden="true">▮▯▯▯</span>
      <span class="text-xs">—</span>
    </span>
  </Tooltip.Trigger>
  <Tooltip.Content>org KC 寄与（Knowledge Coverage）— Coming Soon</Tooltip.Content>
</Tooltip.Root>
```

将来の集約は仕様書 §5.1 の `KC(file, dev)` を開発者軸に平均した
「その開発者の org 全体への KC 寄与」（`contrib(dev) = avg over files of KC(file, dev)`）を想定し、
`GET /api/v1/orgs/{slug}/members/{userId}/kc` で配線する計画。
（§5.1 が定義する `KC(org)` は全ファイル横断の重み付き平均であり別概念。本枠は
開発者単位の寄与を示すため、org 横断値とは区別した独自の派生指標として扱う。）

### ロール変更 dropdown（GitLab `role_selector.vue` / `max_role.vue` に相当）

```svelte
<!-- frontend/src/lib/components/members/member-role-dropdown.svelte -->
<script lang="ts">
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import type { OrgRole } from "$lib/api/schemas";
  let { role, disabled, onchange }:
    { role: OrgRole; disabled: boolean; onchange: (r: OrgRole) => void } = $props();
  const roles: OrgRole[] = ["owner", "admin", "member"];
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger {disabled}>{role}</DropdownMenu.Trigger>
  <DropdownMenu.Content>
    {#each roles as r (r)}
      <DropdownMenu.Item onSelect={() => onchange(r)}>{r}</DropdownMenu.Item>
    {/each}
  </DropdownMenu.Content>
</DropdownMenu.Root>
```

### GitLab の IA をどう写し取るか（末尾固定パターン）

GitLab `project_information_menu.rb` は Manage グルーピング配下に Activity / Labels /
**Members** を並べ、各項目が `super_sidebar_parent: …ManageMenu` を持つ。
`UncategorizedMenu` は「未分類項目を Settings の直前に集約する一時メニュー」であり、
**Settings を常に最下段に固定** する設計思想を体現している。

Rosetta はこの「Settings 末尾固定」だけを規律として採用する：
understand 系の動詞（Galaxy / Matrix / Quiz 等）をサイドバー上段に置き、
権限管理である Members を含む Settings は understand 系より**必ず下**に固定する。
これにより「まず理解する、設定は最後」という Rosetta の価値観をナビ構造で表現する。

## 参考

- 仕様書: `仕様書.md`
  - §5.1 検知シグナル（Knowledge Coverage の算出）— KC 寄与ミニ指標枠の元定義
  - §6.1 ダッシュボード / §6.2 Knowledge Galaxy — KC を共通言語で繋ぐ先の画面
  - §7.1 主要エンティティ — org / membership / role のデータモデル
- 現行フロント実装（配線対象）
  - `frontend/src/lib/api/client.ts` — `getMyMembership` / `listMembers` /
    `inviteMember` / `patchMemberRole` / `removeMember`（実装済み・呼び出し元なし）
  - `frontend/src/lib/api/schemas.ts` — `orgMemberSchema` / `orgRoleSchema`（型は既存）
  - `frontend/src/routes/[org]/+page.svelte` — 現状の org 画面（リポジトリビューアのみ）
  - `frontend/src/routes/[org]/+layout.svelte` / `+layout.ts` — org シェル / 認証ガード
  - `frontend/src/lib/stores/repo-store.svelte.ts` — クラスベース runes ストアの先行例
  - `frontend/messages/ja.json` / `en.json` — Paraglide 文言（ja 主・en 従）
- GitLab 参考実装
  - `gitlab/lib/sidebars/projects/menus/project_information_menu.rb`
    — Members（Manage グルーピング）の IA
  - `gitlab/lib/sidebars/uncategorized_menu.rb` — Settings 直前に挿入する末尾固定パターン
  - `gitlab/app/assets/javascripts/members/components/table/members_table.vue`
    / `member_avatar.vue` / `max_role.vue` / `member_actions.vue` — 一覧・アバター・ロール・操作
  - `gitlab/app/assets/javascripts/members/components/role_selector.vue` — ロール変更 UI
  - `GlAvatar`（shape / entity-id によるカラー生成）— shadcn `avatar` 採用時の色決定の参考
