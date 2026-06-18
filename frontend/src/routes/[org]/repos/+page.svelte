<script lang="ts">
  import { getFileContent, getRepositoryTree, listBranches } from "$lib/api/client";
  import type { Branch, FileContent, Tree } from "$lib/api/schemas";
  import FileTreeComponent from "$lib/components/repo/file-tree.svelte";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";
  import RepoHeader from "$lib/components/repo/repo-header.svelte";
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
  <title>Repos · Rosetta</title>
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
