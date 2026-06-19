# リポジトリビューアを Repos セクションへ退避し GitLab 風に強化する（既存ビューアの GitLab 風リファイン + Dashboard 混線解消）

## 概要

現状 `frontend/src/routes/[org]/+page.svelte` は `<title>Dashboard · Rosetta</title>` を名乗りながら、中身は丸ごとリポジトリビューア（`RepoPicker` / `TechStackPanel` / `FileTree` / `FileViewer`）という **情報設計（IA）の混線** を抱えている。本 issue ではこれを解消し、あわせてビューア各部を GitLab の repository コンポーネント群を参考に磨き込む。具体的には次の 4 点を行う。

1. **退避** — リポジトリビューア一式を `[org]/repos/` 配下へ移設し、`[org]/+page.svelte` を Overview 専用に空ける（Overview の中身は別 issue）。
2. **ツリー強化** — `FileTree` のアイコンを `▶/▼` テキストから GitLab repository ツリー風（folder / doc-text アイコン）に置き換え、段階ロードと **負債密度バッジ枠** を仕込む。
3. **ビューア強化** — `FileViewer` に実構文ハイライトを統合し（`blob_viewers/index.js` のディスパッチ写像に倣った種別別表示）、将来の知識オーバーレイを重畳できる **二層構造** の土台にする。
4. **ヘッダ整形** — repo ヘッダを GitLab `header_area.vue` 風のパンくず + アクション群に整え、`last_commit.vue` 風の最終更新表示を追加。さらに `TechStackPanel` を confidence ベースのバッジ表示に磨く。

単一接続 repo-store（`repo-store.svelte.ts`）はそのまま流用する（MVP はシングルリポジトリ想定）。

## 背景・目的

issue-002 でリポジトリ接続〜ファイル閲覧の一通りを `[org]/+page.svelte` に直接実装した。MVP としては機能していたが、issue-004 でテックスタック解析（`TechStackPanel`）が乗った結果、この 1 ページに「リポジトリ選択」「ファイルツリー」「ファイル閲覧」「スタック解析」が全部詰め込まれ、しかも `<title>` は `Dashboard` を名乗っている。本来 Dashboard（Overview）は仕様書 §6.1 の二軸負債マトリクス・推移グラフ・優先対応リストを置く場所であり、リポジトリビューアとは別物である。この混線を放置すると、後続の Overview 実装が既存ビューアと衝突する。

そこで本 issue でビューアを `[org]/repos/` という専用ルートへ退避させ、`[org]/+page.svelte` を Overview 専用の空き地として明け渡す。退避ついでに、これまで暫定だったツリー / ビューア / ヘッダの見た目を、成熟した OSS である GitLab の repository 系コンポーネントを参考に GitLab 風へ磨き上げる。

### 前提 Issue

- **app-shell-super-sidebar-foundation（issue-005）** — GitLab Super Sidebar 風のアプリシェルとナビゲーションを導入する issue。本 issue が配線する「Repos セクション」のナビ枠はそこで用意される前提とする。issue-005 がマージされていない場合は、暫定的に `[org]/+layout.svelte` のヘッダに `Repos` リンクを足す形でフォールバックする。

### 独自性 — GitLab の丸パクリにしない

GitLab を参考にするのはレイアウトの所作（パンくず・段階ロード・種別別ビューア）までで、Rosetta の核は別にある。GitLab のツリーは行数バッジ（LOC）や CI ステータスを並べるが、Rosetta は同じ枠を **負債密度バッジ** に転用する。`FileTree` の各ノードに「行数バッジ枠」ではなく「負債密度バッジ枠」を最初から仕込んでおき、後続の二軸負債マトリクス（仕様書 §2.3）や Knowledge Coverage（§5.1）と **共通言語** で繋ぐ。同様に `FileViewer` は GitLab の赤緑 diff ビューアには寄せず、ソース層の上に **知識オーバーレイ層（KC ヒートマップ行 + 考古学注釈）** を重ねられる二層構造の土台にする。配色も GitLab 紫ではなく、Rosetta ブランドの **地層アンバー系** で統一する（負債は「埋もれた地層」というメタファ）。本 issue では負債データ自体は流し込まないが、枠と二層構造だけは先に用意しておく。

## タスク

### ルート移設（`[org]/repos/`）

- [ ] `frontend/src/routes/[org]/repos/+page.svelte` を新規作成し、現行 `[org]/+page.svelte` のリポジトリビューア一式（`RepoPicker` / ヘッダ / `FileTree` / `FileViewer` / `TechStackPanel` の配線と `loadTree` / `loadBranches` / `onFileSelect` / `onBranchChange` ロジック）をここへ移設する
- [ ] `<svelte:head>` の `<title>` を `Repos · Rosetta` に変更する
- [ ] issue-005 の Super Sidebar に `Repos` セクションを配線する（リンク先 `/[org]/repos`）。未導入時は `[org]/+layout.svelte` ヘッダに暫定 `Repos` リンクを置くフォールバック

### Overview 専用化（`[org]/+page.svelte` を空ける）

- [ ] `[org]/+page.svelte` からリポジトリビューア関連の import・状態・ロジックを全て撤去する
- [ ] `<title>` を `Dashboard · Rosetta` のまま維持し、中身を **Overview プレースホルダ** に置き換える（仕様書 §6.1 の二軸マトリクス / 推移グラフ / 優先対応リストが入る場所であることを示す軽い案内 + `Repos へ` への導線）。Overview 本体の実装は別 issue

### FileTree のアイコン強化（`frontend/src/lib/components/repo/file-tree.svelte`）

- [ ] `▶/▼` テキストを GitLab repository ツリー風の **folder / folder-open / doc-text アイコン** に置き換える（`@lucide/svelte` の `Folder` / `FolderOpen` / `FileText` 等、または `ui/` 外のラッパで `bits-ui` アイコンを合成）
- [ ] ディレクトリ展開時に子ノードを描画する **段階ロード**（現状の `openDirs` ベースの遅延描画を踏襲しつつ、展開アイコンを folder-open に切り替え）
- [ ] 各ノード行の右端に **負債密度バッジ枠**（`debtSlot` snippet）を確保する。本 issue では空（または `—`）でよいが、後続が密度を流し込めるよう構造を確定する
- [ ] アイコン / バッジの配色を地層アンバー系トークンに合わせる

### FileViewer の構文ハイライト + 二層構造（`frontend/src/lib/components/repo/file-viewer.svelte`）

- [ ] `langFromPath` の拡張子マップを **ビューア種別ディスパッチ** に格上げする（`blob_viewers/index.js` 写像に倣い、`text` / `image` / `binary` / `too_large` / `empty` を判定する `resolveViewer(path, size, content)` を用意）
- [ ] `text` 種別に実構文ハイライタを統合する（`shiki` を推奨。SPA / Tailwind v4 と相性が良い。ビルドサイズ懸念があれば `highlight.js` フォールバック）
- [ ] ソース表示を **二層構造** にする：下層 = ハイライト済みコード、上層 = 知識オーバーレイ用の **行アノテーション枠**（`overlayRow` snippet、本 issue では非表示でよい）
- [ ] `image` / `binary` / `too_large` 種別は GitLab 風に「プレビュー不可 + サイズ表示」のプレースホルダで表示する

### repo ヘッダ（パンくず + last_commit 風）

- [ ] repo ヘッダを `frontend/src/lib/components/repo/repo-header.svelte` として切り出す（現状 `[org]/repos/+page.svelte` 内インライン → コンポーネント化）
- [ ] GitLab `breadcrumbs.vue` 風の **パンくず**（`owner / repo / <選択中ファイルパス>` を `/` 区切りで分割表示）を実装する
- [ ] ブランチ `select` と「切断」をパンくず右のアクション群に整える（GitLab `header_area.vue` のアクション配置に倣う）
- [ ] GitLab `last_commit.vue` 風の **最終更新表示**（`repo.updated_at` を相対時刻 + ステータスドットで表示）を追加する

### TechStackPanel の confidence バッジ強化（`frontend/src/lib/components/repo/tech-stack-panel.svelte`）

- [ ] 現状のクラス直書きバッジを、confidence（`high` / `medium` / `low`）に応じた **GlBadge 風バッジ** に統一する（`badge-variant.ts` ヘルパで variant → クラスを写像、地層アンバー系で濃淡を表現）
- [ ] `high` は実線・濃色、`medium` は淡色、`low` は枠線のみ（点線）など、confidence が一目で分かる三段階表現にする

## 完了条件

- `/[org]/repos` でリポジトリビューア（未接続時 `RepoPicker`、接続時 ヘッダ + `FileTree` + `FileViewer` + `TechStackPanel`）が従来どおり動作すること
- `/[org]`（Overview）にはリポジトリビューアが一切表示されず、Overview プレースホルダと `Repos へ` の導線のみが表示されること（`<title>` は `Dashboard · Rosetta`）
- ナビ（issue-005 の Super Sidebar、未導入時はヘッダ）の `Repos` から `/[org]/repos` へ遷移できること
- `FileTree` のディレクトリ / ファイルが folder / doc-text アイコンで表示され、展開で folder-open に切り替わること。各行に負債密度バッジ枠が存在すること（中身は空でよい）
- `FileViewer` がテキストファイルを構文ハイライト付きで表示し、画像 / バイナリ / 大きすぎるファイルを種別別プレースホルダで表示すること
- repo ヘッダがパンくず + ブランチ select + 切断 + 最終更新で構成され、ファイル選択時にパンくずがそのパスに追従すること
- `TechStackPanel` のバッジが confidence 三段階で視覚的に区別されること
- `cd frontend && bun run check`（svelte-check）と `bun run lint` がパスすること

## 技術詳細

### 画面レイアウト（退避後 `/[org]/repos` 接続済み状態）

```
┌──────────────────────────────────────────────────────────────┐
│ repo-header (header_area 風)                                  │
│  org / repo / src / index.ts        [main ▾] [切断]           │  ← breadcrumbs + actions
│  ● 2 時間前に更新                                              │  ← last_commit 風
├───────────────────────┬──────────────────────────────────────┤
│ TechStackPanel        │ FileViewer（二層構造）               │
│  [TS] [Svelte]  ← high│  ┌────────────────────────────────┐  │
│  [FastAPI]      ← med │  │ overlayRow 層（KC/注釈・後続）  │  │
│ ───────────────────── │  ├────────────────────────────────┤  │
│ FileTree              │  │ source 層（shiki ハイライト）   │  │
│  📂 src/         [—]  │  │  1  import { ... }              │  │
│   📄 index.ts    [—]  │  │  2  ...                         │  │
│  📁 tests/       [—]  │  └────────────────────────────────┘  │
│        ↑ folder/doc   │           ↑ 負債密度バッジ枠 [—]      │
└───────────────────────┴──────────────────────────────────────┘
```

### コンポーネント構成（移設後）

```
frontend/src/routes/[org]/
  +page.svelte            ← Overview 専用に空ける（プレースホルダのみ）
  +layout.svelte          ← （フォールバック時）Repos リンク
  repos/
    +page.svelte          ← 退避後のリポジトリビューア（旧 +page.svelte のロジック）

frontend/src/lib/components/repo/
  repo-picker.svelte      ← 流用（変更なし）
  repo-header.svelte      ← 新規：breadcrumbs + actions + last_commit 風
  file-tree.svelte        ← 強化：folder/doc-text アイコン + debtSlot
  file-viewer.svelte      ← 強化：種別ディスパッチ + shiki + overlayRow（二層）
  tech-stack-panel.svelte ← 強化：confidence バッジ

frontend/src/lib/
  stores/repo-store.svelte.ts  ← 流用（単一接続のまま、変更なし）
  components/repo/badge-variant.ts  ← 新規：confidence → クラス写像
```

### ビューア種別ディスパッチ（`blob_viewers/index.js` を参考）

GitLab の `loadViewer(type, isUsingLfs, isTooLarge)` 写像に倣い、Rosetta は軽量に種別を解決する。動的 import ではなく単純な分岐で十分。

```typescript
// file-viewer.svelte 内
type ViewerKind = "text" | "image" | "binary" | "too_large" | "empty";

const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "avif"]);
const TOO_LARGE_BYTES = 1024 * 1024; // 1 MB

function resolveViewer(path: string, size: number, content: string | null): ViewerKind {
  if (size === 0) return "empty";
  if (size > TOO_LARGE_BYTES) return "too_large";
  const ext = path.split(".").at(-1)?.toLowerCase() ?? "";
  if (IMAGE_EXT.has(ext)) return "image";
  if (content === null) return "binary"; // API がデコード不能で content=null を返した
  return "text";
}
```

### FileTree のアイコン + 負債密度バッジ枠

現状はテキスト `▶/▼` と空 span。これをアイコン + バッジ枠に置き換える。`buildTree` / `openDirs` の段階描画ロジックはそのまま流用する。

```svelte
<!-- file-tree.svelte（tree ノード行の抜粋イメージ） -->
{#if node.type === "tree"}
  <button onclick={() => toggle(node.path)} class="...">
    {#if openDirs.has(node.path)}
      <FolderOpen class="size-4 text-amber-600" />
    {:else}
      <Folder class="size-4 text-amber-600" />
    {/if}
    <span class="truncate">{node.name}</span>
    {@render debtSlot(node.path)}  <!-- 負債密度バッジ枠（後続が密度を流す） -->
  </button>
{:else}
  <button onclick={() => onfileselect(node.path)} class="...">
    <FileText class="size-4 text-muted-foreground" />
    <span class="truncate">{node.name}</span>
    {@render debtSlot(node.path)}
  </button>
{/if}

{#snippet debtSlot(_path: string)}
  <!-- 本 issue では空。後続: <span class="rounded bg-amber-500/20 ...">{density}</span> -->
  <span class="ml-auto text-xs text-muted-foreground/40">—</span>
{/snippet}
```

### repo ヘッダのパンくず（`breadcrumbs.vue` 風）

GitLab の `pathLinks`（`currentPath.split("/")` を累積パスに reduce）を Svelte 5 runes で実装する。

```typescript
// repo-header.svelte 内
type Crumb = { name: string; path: string };

const crumbs = $derived.by<Crumb[]>(() => {
  const base: Crumb[] = [
    { name: repo.connected!.owner, path: "" },
    { name: repo.connected!.name, path: "" },
  ];
  if (!selectedPath) return base;
  const parts = selectedPath.split("/").filter(Boolean);
  return [
    ...base,
    ...parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join("/") })),
  ];
});
```

`last_commit.vue` 風の最終更新は `repo.connected.updated_at` を相対時刻（`Intl.RelativeTimeFormat`）+ ステータスドット（`●`、緑 = 正常）で表示する。GitLab のように CI パイプライン状態は持たないため、ドットは「データ取得済み」を示す軽い表現に留める。

### confidence バッジ写像（TechStackPanel）

```typescript
// components/repo/badge-variant.ts
type Confidence = "high" | "medium" | "low";

export const confidenceBadge: Record<Confidence, string> = {
  // 地層アンバー系で濃淡を表現（GitLab 紫は使わない）
  high: "bg-amber-500/20 text-amber-900 font-medium ring-1 ring-amber-500/40",
  medium: "bg-amber-500/10 text-amber-800/80",
  low: "border border-dashed border-amber-500/40 text-muted-foreground",
};
```

`tech-stack-panel.svelte` の言語・カテゴリ各 `<span>` のクラス直書きを `confidenceBadge[item.confidence]` に差し替える。

### 既存実装からの変更点まとめ

| 対象 | 現状 | 変更後 |
|---|---|---|
| ルート | `[org]/+page.svelte` がビューア（`title: Dashboard`） | `[org]/repos/+page.svelte` がビューア（`title: Repos`）、`[org]/+page.svelte` は Overview 空き地 |
| FileTree アイコン | `▶/▼` テキスト + 空 span | folder / folder-open / doc-text アイコン + 負債密度バッジ枠 |
| FileViewer | `<pre><code class="language-…">` 素のテキスト | 種別ディスパッチ + shiki 構文ハイライト + overlayRow 二層構造 |
| repo ヘッダ | `full_name` + select + 切断（インライン） | `repo-header.svelte`：パンくず + アクション群 + last_commit 風最終更新 |
| TechStackPanel バッジ | クラス直書き 2 段階 | `confidenceBadge` 写像で high/medium/low 三段階・地層アンバー系 |
| repo-store | 単一接続 | 変更なし（MVP シングルリポジトリ） |

### API・型

本 issue は **フロントエンドのリファクタのみ** で、バックエンド API と Zod スキーマ（`frontend/src/lib/api/schemas.ts`）は変更しない。利用するのは issue-002 / issue-003 で定義済みの以下のみ。

- `getRepositoryTree(owner, repo, branch)` → `Tree`（`treeItemSchema`: `path` / `type` / `size`）
- `getFileContent(owner, repo, path, ref)` → `FileContent`（`content` は非テキスト時 `null`）
- `listBranches(owner, repo)` → `BranchList`
- `getStack(owner, repo)` / `analyzeStack(owner, repo)` → `TechStack`（`techItemSchema`: `name` / `confidence`）
- `repo`（`repo-store.svelte.ts`）: `connected` / `selectedBranch` / `connect()` / `disconnect()`

負債密度・知識オーバーレイのデータソースは本 issue では未配線（枠のみ）。後続 issue でツリー / ビューアに密度・KC を流し込む。

## 参考

- 仕様書: `仕様書.md` §6.1 ダッシュボード（Overview に入る二軸マトリクス / 推移グラフ / 優先対応リスト — `[org]/+page.svelte` の行き先）、§2.3 二軸負債モデル・§5.1 Knowledge Coverage（負債密度バッジ枠 / 知識オーバーレイの接続先）
- 前提 issue: `docs/issue/005-...`（app-shell-super-sidebar-foundation — Repos セクションのナビ枠）
- 関連 issue: `docs/issue/002-repository-connect-and-viewer.md`（移設元の実装）、`docs/issue/003-tech-stack-analysis.md`・`docs/issue/004-adk-stack-analysis-agent.md`（TechStackPanel が表示する解析結果）
- GitLab 参考実装:
  - `gitlab/app/assets/javascripts/repository/components/tree_content.vue` — 段階ロード付きツリー + README プレビュー
  - `gitlab/app/assets/javascripts/repository/components/blob_viewers/index.js` — 種別別ビューアディスパッチ（`loadViewer`）
  - `gitlab/app/assets/javascripts/repository/components/header_area/breadcrumbs.vue` — パンくず（`pathLinks` の累積パス reduce）
  - `gitlab/app/assets/javascripts/repository/components/header_area.vue` — ヘッダのアクション群配置
  - `gitlab/app/assets/javascripts/repository/components/last_commit.vue` — 最終更新 + ステータスアイコン
- 現行フロント実装（移設・強化対象）:
  - `frontend/src/routes/[org]/+page.svelte`
  - `frontend/src/lib/components/repo/{repo-picker,file-tree,file-viewer,tech-stack-panel}.svelte`
  - `frontend/src/lib/stores/repo-store.svelte.ts`
  - `frontend/src/lib/api/{schemas,client}.ts`
