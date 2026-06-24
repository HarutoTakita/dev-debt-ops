<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { getFileContent, getRepositoryTree, listBranches, listDebts } from "$lib/api/client";
  import type { Branch, CodeDebt, FileContent, Tree } from "$lib/api/schemas";
  import FileTreeComponent from "$lib/components/repo/file-tree.svelte";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";
  import CodeDebtPanel from "$lib/components/repo/code-debt-panel.svelte";
  import RepoHeader from "$lib/components/repo/repo-header.svelte";
  import RepoPicker from "$lib/components/repo/repo-picker.svelte";
  import TechStackPanel from "$lib/components/repo/tech-stack-panel.svelte";
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
  let branches = $state<Branch[]>([]);
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
  const openCount = $derived(codeDebts.filter((d) => d.status === "open").length);
  const selectedDebts = $derived(selectedPath ? (debtsByPath.get(selectedPath) ?? []) : []);

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
  // 解析（コード負債検知）の完了で密度バッジ／パネルを再取得（issue 049 の仕組みを流用）。
  refreshOnStageComplete(["detect_code"], loadDebts);

  async function loadTree(branch: string) {
    if (!repo.connected) return;
    treeLoading = true;
    selectedPath = null;
    fileContent = null;
    try {
      tree = await getRepositoryTree(repo.connected.owner, repo.connected.name, branch);
    } catch {
      tree = null;
    } finally {
      treeLoading = false;
    }
  }

  async function loadBranches() {
    if (!repo.connected) return;
    try {
      const result = await listBranches(repo.connected.owner, repo.connected.name);
      branches = result.branches;
    } catch {
      branches = [];
    }
  }

  async function onFileSelect(path: string) {
    if (!repo.connected) return;
    selectedPath = path;
    fileLoading = true;
    fileContent = null;
    try {
      fileContent = await getFileContent(repo.connected.owner, repo.connected.name, path, repo.selectedBranch);
    } catch {
      fileContent = null;
    } finally {
      fileLoading = false;
    }
  }

  async function onBranchChange(branch: string) {
    repo.selectedBranch = branch;
    await loadTree(branch);
  }

  $effect(() => {
    if (repo.connected) {
      loadBranches();
      loadTree(repo.selectedBranch);
    } else {
      tree = null;
      branches = [];
      selectedPath = null;
      fileContent = null;
    }
  });
</script>

<svelte:head>
  <title>{m.nav_repos()} · DevDebtOps</title>
</svelte:head>

{#if !repo.connected}
  <div class="flex h-full items-center justify-center">
    <RepoPicker onselect={(r) => repo.connect(r)} />
  </div>
{:else}
  <div class="flex h-full flex-col">
    <RepoHeader
      {branches}
      selectedBranch={repo.selectedBranch}
      {selectedPath}
      onbranchchange={onBranchChange}
      ondisconnect={() => repo.disconnect()}
    />

    <div class="flex flex-1 overflow-hidden">
      <aside class="flex w-64 shrink-0 flex-col overflow-y-auto border-r" data-tour="repos-tree">
        <TechStackPanel owner={repo.connected.owner} repo={repo.connected.name} />
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
        <div class="flex items-center justify-between gap-2 border-b px-3 py-1.5 text-xs">
          <span class="text-muted-foreground tabular-nums">{m.code_improve_open_count({ count: openCount })}</span>
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
          <FileViewer
            path={selectedPath}
            content={fileContent?.content ?? null}
            size={fileContent?.size ?? 0}
            loading={fileLoading}
          />
        </div>

        {#if selectedPath}
          <div class="max-h-64 shrink-0 overflow-y-auto border-t bg-surface-sunken/40">
            <CodeDebtPanel {orgSlug} {projectSlug} debts={selectedDebts} onchanged={loadDebts} />
          </div>
        {/if}
      </main>
    </div>
  </div>
{/if}
