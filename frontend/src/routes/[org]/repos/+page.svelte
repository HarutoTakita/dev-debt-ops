<script lang="ts">
  import { getFileContent, getRepositoryTree, listBranches } from "$lib/api/client";
  import type { Branch, FileContent, Tree } from "$lib/api/schemas";
  import FileTreeComponent from "$lib/components/repo/file-tree.svelte";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";
  import RepoPicker from "$lib/components/repo/repo-picker.svelte";
  import TechStackPanel from "$lib/components/repo/tech-stack-panel.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";

  let tree = $state<Tree | null>(null);
  let branches = $state<Branch[]>([]);
  let selectedPath = $state<string | null>(null);
  let fileContent = $state<FileContent | null>(null);
  let fileLoading = $state(false);
  let treeLoading = $state(false);

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

  async function onBranchChange(e: Event) {
    const branch = (e.target as HTMLSelectElement).value;
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
  <title>リポジトリ · Rosetta</title>
</svelte:head>

{#if !repo.connected}
  <div class="flex h-full items-center justify-center">
    <RepoPicker onselect={(r) => repo.connect(r)} />
  </div>
{:else}
  <div class="flex h-full flex-col">
    <div class="flex items-center gap-3 border-b px-4 py-2">
      <span class="text-sm font-medium">{repo.connected.full_name}</span>
      <select onchange={onBranchChange} value={repo.selectedBranch} class="rounded border px-2 py-1 text-sm">
        {#each branches as b (b.name)}
          <option value={b.name}>{b.name}{b.is_default ? " (default)" : ""}</option>
        {/each}
        {#if branches.length === 0}
          <option value={repo.selectedBranch}>{repo.selectedBranch}</option>
        {/if}
      </select>
      <button onclick={() => repo.disconnect()} class="ml-auto text-sm text-muted-foreground hover:text-foreground">
        切断
      </button>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <aside class="flex w-64 shrink-0 flex-col overflow-y-auto border-r">
        <TechStackPanel owner={repo.connected.owner} repo={repo.connected.name} />
        {#if treeLoading}
          <p class="p-4 text-sm text-muted-foreground">読み込み中...</p>
        {:else if tree}
          <FileTreeComponent tree={tree.tree} {selectedPath} onfileselect={onFileSelect} />
        {/if}
      </aside>

      <main class="flex-1 overflow-hidden">
        <FileViewer
          path={selectedPath}
          content={fileContent?.content ?? null}
          size={fileContent?.size ?? 0}
          loading={fileLoading}
        />
      </main>
    </div>
  </div>
{/if}
