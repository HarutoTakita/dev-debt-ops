<script lang="ts">
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import Lock from "@lucide/svelte/icons/lock";
  import Plus from "@lucide/svelte/icons/plus";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { Button } from "$lib/components/ui/button";
  import { project } from "$lib/stores/project-store.svelte";
  import { projectCreate } from "$lib/stores/project-create.svelte";
  import { projectIconColor } from "$lib/stores/project-icon";
  import type { Project } from "$lib/api/schemas";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  const skeletonCards = Array.from({ length: 6 }, (_v, i) => i);

  const orgSlug = $derived(page.params.org ?? "");

  // org 配下のプロジェクト（= 観測対象リポジトリ）一覧を読み込む。
  $effect(() => {
    if (orgSlug) project.loadList(orgSlug);
  });

  const projects = $derived(project.list);
</script>

{#snippet projectCard(p: Project)}
  <a
    href={resolve(`/${orgSlug}/${p.slug}`)}
    class="group flex flex-col gap-2 rounded-lg border border-sidebar-border bg-surface-sunken p-4 transition-colors hover:border-debt-knowledge/50 hover:bg-accent/40"
  >
    <div class="flex items-center gap-2">
      <span class={cn("flex size-8 shrink-0 items-center justify-center rounded", projectIconColor(p))}>
        <FolderGit2 class="size-4" />
      </span>
      <span class="min-w-0 flex-1 truncate font-medium">{p.name}</span>
      {#if p.repo_private}
        <Lock class="size-3.5 shrink-0 text-muted-foreground" />
      {/if}
    </div>
    <span class="truncate font-mono text-xs text-muted-foreground">{p.repo_full_name}</span>
  </a>
{/snippet}

<svelte:head>
  <title>{m.project_home_title()} · DevDebtOps</title>
</svelte:head>

<div class="mx-auto w-full max-w-5xl px-6 py-10">
  <div class="flex items-end justify-between gap-4">
    <div>
      <h1 class="font-display text-2xl font-semibold tracking-tight">{m.project_home_title()}</h1>
      <p class="mt-1 text-sm text-muted-foreground">{m.project_home_subtitle()}</p>
    </div>
    {#if projects.length > 0}
      <Button onclick={() => (projectCreate.open = true)}>
        <Plus class="size-4" />
        {m.project_home_new()}
      </Button>
    {/if}
  </div>

  {#if project.loading && projects.length === 0}
    <div class="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
      {#each skeletonCards as i (i)}
        <div class="flex flex-col gap-2 rounded-lg border border-sidebar-border bg-surface-sunken p-4">
          <div class="flex items-center gap-2">
            <Skeleton class="size-8 rounded" />
            <Skeleton class="h-4 flex-1" />
          </div>
          <Skeleton class="h-3 w-2/3" />
        </div>
      {/each}
    </div>
  {:else if projects.length === 0}
    <div
      class="mx-auto mt-12 flex max-w-md flex-col items-center gap-4 rounded-lg border border-dashed border-sidebar-border py-16 text-center"
    >
      <span class="flex size-14 items-center justify-center rounded-full bg-debt-knowledge/15 text-debt-knowledge">
        <FolderGit2 class="size-7" />
      </span>
      <h2 class="font-display text-lg">{m.project_home_empty_title()}</h2>
      <p class="max-w-xs text-sm text-muted-foreground">{m.project_home_empty_desc()}</p>
      <Button onclick={() => (projectCreate.open = true)}>
        <Plus class="size-4" />
        {m.project_home_new()}
      </Button>
    </div>
  {:else}
    <div class="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {#each projects as p (p.id)}
        {@render projectCard(p)}
      {/each}
    </div>
  {/if}
</div>
