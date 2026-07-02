<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { getFileContent, getRepositoryTree, listDebts } from "$lib/api/client";
  import type { CodeDebt, FileContent, Tree } from "$lib/api/schemas";
  import FileTreeComponent from "$lib/components/repo/file-tree.svelte";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";
  import CodeLines from "$lib/components/learning/code-lines.svelte";
  import CodeDebtPanel from "$lib/components/repo/code-debt-panel.svelte";
  import RepoHeader from "$lib/components/repo/repo-header.svelte";
  import RepoPicker from "$lib/components/repo/repo-picker.svelte";
  import PageHeading from "$lib/components/shell/page-heading.svelte";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // ゴーストツリー（インデント付き行）の幅・字下げプリセット。
  const ghostTree = [
    "w-32 ml-0",
    "w-40 ml-3",
    "w-28 ml-3",
    "w-44 ml-6",
    "w-36 ml-6",
    "w-24 ml-3",
    "w-40 ml-0",
    "w-32 ml-3",
  ];

  let tree = $state<Tree | null>(null);
  let selectedPath = $state<string | null>(null);
  let fileContent = $state<FileContent | null>(null);
  let fileLoading = $state(false);
  let treeLoading = $state(false);

  // 技術負債（コード）をプロジェクト単位で取得し、ファイルツリーの密度バッジ＋ファイル別返済パネルに使う。
  let codeDebts = $state<CodeDebt[]>([]);
  const debtsByPath = $derived.by(() => {
    const groups: Record<string, CodeDebt[]> = {};
    for (const d of codeDebts) (groups[d.file_path] ??= []).push(d);
    return new Map(Object.entries(groups));
  });
  const debtCountByPath = $derived(new Map([...debtsByPath].map(([p, list]) => [p, list.length])));
  const selectedDebts = $derived(selectedPath ? (debtsByPath.get(selectedPath) ?? []) : []);

  // 負債ブロックのクリックで、その抜粋(code_snippet)に対応する行範囲をコードビューでハイライトする。
  let highlightStart = $state(0);
  let highlightEnd = $state(0);
  let activeDebtId = $state<string | null>(null);
  // ソース（テキスト）なら行番号つきコードビューでハイライト可能。画像/バイナリは FileViewer に委譲。
  const isTextFile = $derived(
    !!selectedPath &&
      !fileLoading &&
      fileContent?.content != null &&
      !/\.(png|jpe?g|gif|webp|svg|avif)$/i.test(selectedPath),
  );

  function highlightDebt(debt: CodeDebt) {
    activeDebtId = debt.id;
    const text = fileContent?.content ?? "";
    const snippet = debt.code_snippet ?? "";
    if (!text || !snippet) {
      highlightStart = highlightEnd = 0;
      return;
    }
    // 抜粋の先頭の非空行をファイル本文から探し、見つかった位置から抜粋行数ぶんをハイライト。
    const lines = text.split("\n");
    const firstLine = (snippet.split("\n").find((l) => l.trim()) ?? "").trim();
    const idx = firstLine ? lines.findIndex((l) => l.includes(firstLine)) : -1;
    const start = idx >= 0 ? idx + 1 : 1;
    const snippetLines = snippet.replace(/\n+$/, "").split("\n").length;
    highlightStart = start;
    highlightEnd = Math.min(lines.length, start + snippetLines - 1);
  }

  function loadDebts() {
    if (!orgSlug || !projectSlug) return;
    listDebts(orgSlug, projectSlug, { kind: ["code"] }, { key: "severity", dir: "desc" })
      .then((res) => {
        codeDebts = res.debts.filter((d): d is CodeDebt => d.kind === "code");
      })
      .catch(() => {
        codeDebts = [];
      });
  }

  $effect(() => {
    void orgSlug;
    void projectSlug;
    loadDebts();
  });
  // 解析（agentic がコード負債を生成）の完了で密度バッジ／パネルを再取得（issue 049/069）。
  refreshOnStageComplete(["agentic"], loadDebts);

  // stale-while-revalidate: キャッシュがあれば即表示（スピナーなし）し、裏で最新を取得して差し替える。
  // 同一リポジトリへ再訪したときの「リポジトリ表示が遅い」を解消する。初回のみ GitHub 取得を待つ。
  async function loadTree(branch: string) {
    if (!repo.connected) return;
    const { owner, name } = repo.connected;
    const key = `${owner}/${name}@${branch}`;
    const cached = repo.treeCache.get(key);
    selectedPath = null;
    fileContent = null;
    if (cached) {
      tree = cached;
      treeLoading = false;
    } else {
      tree = null;
      treeLoading = true;
    }
    try {
      const fresh = await getRepositoryTree(owner, name, branch);
      repo.treeCache.set(key, fresh);
      tree = fresh;
    } catch {
      if (!cached) tree = null; // キャッシュがあれば表示は維持
    } finally {
      treeLoading = false;
    }
  }

  async function onFileSelect(path: string) {
    if (!repo.connected) return;
    selectedPath = path;
    fileLoading = true;
    fileContent = null;
    highlightStart = highlightEnd = 0; // ファイル切替でハイライトをリセット
    activeDebtId = null;
    try {
      fileContent = await getFileContent(repo.connected.owner, repo.connected.name, path, repo.selectedBranch);
    } catch {
      fileContent = null;
    } finally {
      fileLoading = false;
    }
  }

  $effect(() => {
    if (repo.connected) {
      loadTree(repo.selectedBranch);
    } else {
      tree = null;
      selectedPath = null;
      fileContent = null;
    }
  });

  // 学習プランの「チーム内資産」リンク（?path=...）から該当ファイルを開く（ツリー読込後に適用）。
  let appliedPath: string | null = null;
  $effect(() => {
    const path = page.url.searchParams.get("path");
    if (path && path !== appliedPath && tree && repo.connected) {
      appliedPath = path;
      void onFileSelect(path);
    }
  });
</script>

<svelte:head>
  <title>{m.matrix_title()} · DevDebtOps</title>
</svelte:head>

{#if !repo.connected}
  <div class="flex h-full items-center justify-center">
    <RepoPicker onselect={(r) => repo.connect(r)} />
  </div>
{:else}
  <div class="flex h-full flex-col">
    <div class="shrink-0 px-4 pt-3 pb-1">
      <PageHeading title={m.matrix_title()} description={m.page_repos_desc()} />
    </div>
    <RepoHeader {selectedPath} />

    <!-- モバイルは縦積み（ツリー上・ビューア下）、lg 以上で従来の左右 2 ペイン。 -->
    <div class="flex flex-1 flex-col overflow-hidden lg:flex-row">
      <aside
        class="flex max-h-56 w-full shrink-0 flex-col overflow-y-auto border-b lg:max-h-none lg:w-64 lg:border-r lg:border-b-0"
        data-tour="repos-tree"
      >
        {#if treeLoading}
          <div class="flex flex-col gap-2 p-3" aria-busy="true">
            {#each ghostTree as w (w)}
              <Skeleton class={`h-4 ${w}`} />
            {/each}
          </div>
        {:else if tree}
          <FileTreeComponent tree={tree.tree} {selectedPath} {debtCountByPath} onfileselect={onFileSelect} />
        {/if}
      </aside>

      <main class="flex flex-1 flex-col overflow-hidden" data-tour="repos-viewer">
        <div class="flex items-center justify-end gap-2 border-b px-3 py-1.5 text-xs">
          {#if codeDebts.length === 0}
            <a
              href={resolve(`/${orgSlug}/${projectSlug}`)}
              class="inline-flex h-7 items-center rounded-md border px-2.5 text-xs font-medium hover:bg-accent/40"
            >
              {m.analysis_run_cta()}
            </a>
          {/if}
        </div>

        <div class="min-h-0 flex-1 overflow-hidden">
          {#if isTextFile && fileContent?.content != null}
            <CodeLines
              content={fileContent.content}
              path={selectedPath ?? ""}
              {highlightStart}
              {highlightEnd}
              containerClass="h-full overflow-auto font-mono text-xs"
            />
          {:else}
            <FileViewer
              path={selectedPath}
              content={fileContent?.content ?? null}
              size={fileContent?.size ?? 0}
              loading={fileLoading}
            />
          {/if}
        </div>

        {#if selectedPath}
          <div class="max-h-40 shrink-0 overflow-y-auto border-t bg-surface-sunken/40" data-tour="repos-debts">
            <CodeDebtPanel
              {orgSlug}
              {projectSlug}
              debts={selectedDebts}
              onhighlight={highlightDebt}
              activeId={activeDebtId}
            />
          </div>
        {/if}
      </main>
    </div>
  </div>
{/if}
