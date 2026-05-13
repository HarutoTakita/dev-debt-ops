<script lang="ts">
  import type { TreeItem } from "$lib/api/schemas";
  import { SvelteMap, SvelteSet } from "svelte/reactivity";

  type Props = {
    tree: TreeItem[];
    selectedPath: string | null;
    onfileselect: (path: string) => void;
  };

  const { tree, selectedPath, onfileselect }: Props = $props();

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

  function toggle(path: string) {
    if (openDirs.has(path)) {
      openDirs.delete(path);
    } else {
      openDirs.add(path);
    }
  }
</script>

{#snippet nodeList(nodes: TreeNode[])}
  <ul class="pl-3">
    {#each nodes as node (node.path)}
      <li>
        {#if node.type === "tree"}
          <button
            onclick={() => toggle(node.path)}
            class="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent"
          >
            <span class="w-3 text-xs text-muted-foreground">{openDirs.has(node.path) ? "▼" : "▶"}</span>
            <span>{node.name}/</span>
          </button>
          {#if openDirs.has(node.path)}
            {@render nodeList(node.children)}
          {/if}
        {:else}
          <button
            onclick={() => onfileselect(node.path)}
            class="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-accent {selectedPath ===
            node.path
              ? 'bg-accent font-medium'
              : ''}"
          >
            <span class="w-3"></span>
            <span>{node.name}</span>
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
