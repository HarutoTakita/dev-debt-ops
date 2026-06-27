<script lang="ts">
  import Folder from "@lucide/svelte/icons/folder";
  import FolderOpen from "@lucide/svelte/icons/folder-open";
  import FileText from "@lucide/svelte/icons/file-text";
  import type { TreeItem } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import { SvelteMap, SvelteSet } from "svelte/reactivity";

  type Props = {
    tree: TreeItem[];
    selectedPath: string | null;
    onfileselect: (path: string) => void;
    /** ファイルパス → 技術負債件数（「コード改善」で密度バッジに使う）。 */
    debtCountByPath?: Map<string, number>;
  };

  const { tree, selectedPath, onfileselect, debtCountByPath }: Props = $props();

  type TreeNode = {
    name: string;
    path: string;
    type: "blob" | "tree";
    children: TreeNode[];
  };

  function buildTree(items: TreeItem[]): TreeNode[] {
    const nodeMap = new SvelteMap<string, TreeNode>();
    const roots: TreeNode[] = [];

    for (const item of items) {
      const parts = item.path.split("/");
      for (let i = 0; i < parts.length; i++) {
        const path = parts.slice(0, i + 1).join("/");
        if (!nodeMap.has(path)) {
          const node: TreeNode = {
            name: parts[i],
            path,
            type: i === parts.length - 1 ? (item.type as "blob" | "tree") : "tree",
            children: [],
          };
          nodeMap.set(path, node);
          if (i === 0) {
            roots.push(node);
          } else {
            const parentPath = parts.slice(0, i).join("/");
            nodeMap.get(parentPath)?.children.push(node);
          }
        }
      }
    }

    function sortNodes(nodes: TreeNode[]): TreeNode[] {
      return nodes
        .sort((a, b) => {
          if (a.type !== b.type) return a.type === "tree" ? -1 : 1;
          return a.name.localeCompare(b.name);
        })
        .map((n) => ({ ...n, children: sortNodes(n.children) }));
    }

    return sortNodes(roots);
  }

  const rootNodes = $derived(buildTree(tree));
  const openDirs = new SvelteSet<string>();

  // ファイルは自身の件数、ディレクトリは配下ファイルの合計（負債密度のロールアップ）。
  function nodeDebtCount(node: TreeNode): number {
    if (node.type === "blob") return debtCountByPath?.get(node.path) ?? 0;
    return node.children.reduce((sum, c) => sum + nodeDebtCount(c), 0);
  }

  function toggle(path: string) {
    if (openDirs.has(path)) {
      openDirs.delete(path);
    } else {
      openDirs.add(path);
    }
  }

  const rowClass = "flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-sm hover:bg-accent";
</script>

<!-- 負債密度バッジ枠。技術負債の件数をここに表示（「コード改善」で密度を可視化）。0 件は控えめに "—"。 -->
{#snippet debtSlot(count: number)}
  {#if count > 0}
    <span
      class="ml-auto shrink-0 rounded-full bg-debt-code/15 px-1.5 text-[10px] font-medium text-debt-code tabular-nums"
    >
      {count}
    </span>
  {:else}
    <span class="ml-auto shrink-0 text-xs text-muted-foreground/30 tabular-nums">—</span>
  {/if}
{/snippet}

{#snippet nodeList(nodes: TreeNode[])}
  <ul class="pl-3">
    {#each nodes as node (node.path)}
      <li>
        {#if node.type === "tree"}
          <button onclick={() => toggle(node.path)} class={rowClass}>
            {#if openDirs.has(node.path)}
              <FolderOpen class="size-4 shrink-0 text-debt-code" />
            {:else}
              <Folder class="size-4 shrink-0 text-debt-code" />
            {/if}
            <span class="flex-1 truncate">{node.name}</span>
            {@render debtSlot(nodeDebtCount(node))}
          </button>
          {#if openDirs.has(node.path)}
            {@render nodeList(node.children)}
          {/if}
        {:else}
          <button
            onclick={() => onfileselect(node.path)}
            class={cn(rowClass, selectedPath === node.path && "bg-accent font-medium")}
          >
            <FileText class="size-4 shrink-0 text-muted-foreground" />
            <span class="flex-1 truncate">{node.name}</span>
            {@render debtSlot(nodeDebtCount(node))}
          </button>
        {/if}
      </li>
    {/each}
  </ul>
{/snippet}

<div class="h-full overflow-y-auto p-2">
  {#if tree.length === 0}
    <p class="px-2 py-4 text-sm text-muted-foreground">ファイルがありません</p>
  {:else}
    {@render nodeList(rootNodes)}
  {/if}
</div>
