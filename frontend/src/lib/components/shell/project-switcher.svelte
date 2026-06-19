<script lang="ts">
  import ChevronsUpDown from "@lucide/svelte/icons/chevrons-up-down";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import Plus from "@lucide/svelte/icons/plus";
  import Search from "@lucide/svelte/icons/search";
  import Lock from "@lucide/svelte/icons/lock";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import * as Popover from "$lib/components/ui/popover";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { project } from "$lib/stores/project-store.svelte";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import type { Project } from "$lib/api/schemas";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import * as m from "$lib/paraglide/messages";

  const skeletonRows = Array.from({ length: 5 }, (_v, i) => i);

  const orgSlug = $derived(page.params.org ?? "");
  const current = $derived(project.current);

  let open = $state(false);
  let query = $state("");

  // パネルを開いたら org のプロジェクト一覧をロードする（GitLab context switcher の遅延ロードに相当）。
  $effect(() => {
    if (open && orgSlug) {
      project.loadList(orgSlug);
    }
  });

  function matches(p: Project): boolean {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return p.name.toLowerCase().includes(q) || p.repo_full_name.toLowerCase().includes(q);
  }

  const recent = $derived(project.recentProjects(orgSlug).filter((p) => matches(p) && p.id !== current?.id));
  const all = $derived(project.list.filter(matches));

  async function navigateTo(slug: string) {
    open = false;
    query = "";
    await goto(resolve(`/${orgSlug}/${slug}`));
  }

  async function createNew() {
    open = false;
    query = "";
    await goto(resolve(`/${orgSlug}/projects/new`));
  }
</script>

<Popover.Root bind:open>
  <Popover.Trigger>
    {#snippet child({ props })}
      {#if sidebar.collapsed}
        <Tooltip.Root>
          <Tooltip.Trigger>
            {#snippet child({ props: tip })}
              <button
                {...props}
                {...tip}
                class="flex h-10 w-full items-center justify-center rounded-md border border-sidebar-border bg-background/40 text-muted-foreground hover:text-foreground"
                aria-label={current?.name ?? m.project_switcher_select()}
              >
                <FolderGit2 class="size-4" />
              </button>
            {/snippet}
          </Tooltip.Trigger>
          <Tooltip.Content side="right">{current?.name ?? m.project_switcher_select()}</Tooltip.Content>
        </Tooltip.Root>
      {:else}
        <button
          {...props}
          class="flex w-full items-center gap-2 rounded-md border border-sidebar-border bg-background/40 px-2.5 py-2 text-left transition-colors hover:bg-accent/50"
        >
          <span
            class="flex size-7 shrink-0 items-center justify-center rounded bg-debt-knowledge/15 text-debt-knowledge"
          >
            <FolderGit2 class="size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{current?.name ?? m.project_switcher_select()}</span>
            {#if current}
              <span class="block truncate font-mono text-[11px] text-muted-foreground">{current.repo_full_name}</span>
            {/if}
          </span>
          <ChevronsUpDown class="size-4 shrink-0 text-muted-foreground" />
        </button>
      {/if}
    {/snippet}
  </Popover.Trigger>

  <Popover.Content align="start" sideOffset={6} class="w-72 p-0">
    <div class="flex items-center gap-2 border-b border-sidebar-border px-3 py-2">
      <Search class="size-4 shrink-0 text-muted-foreground" />
      <input
        bind:value={query}
        placeholder={m.project_switcher_search()}
        class="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>

    <div class="max-h-80 overflow-y-auto p-1.5">
      {#if project.loading}
        <!-- 読込中: リスト形スケルトン（確定空と区別する） -->
        <div class="flex flex-col gap-1 p-1" aria-busy="true">
          {#each skeletonRows as i (i)}
            <div class="flex items-center gap-2 px-1.5 py-1.5">
              <Skeleton class="size-4 rounded" />
              <Skeleton class="h-4 flex-1" />
            </div>
          {/each}
        </div>
      {:else if project.error !== null}
        <!-- 失敗: 再試行（Popover を開いた状態で loadList を再実行） -->
        <div class="flex flex-col items-center gap-2 px-2 py-6 text-center">
          <p class="text-sm text-destructive">{m.project_switcher_error()}</p>
          <button
            type="button"
            onclick={() => project.loadList(orgSlug)}
            class="rounded-md border px-3 py-1 text-xs hover:bg-accent/50"
          >
            {m.common_retry()}
          </button>
        </div>
      {:else}
        {#if recent.length > 0}
          <div class="px-2 py-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            {m.project_switcher_recent()}
          </div>
          {#each recent as p (p.id)}
            {@render row(p)}
          {/each}
          <div class="my-1 border-t border-sidebar-border"></div>
        {/if}

        <div class="px-2 py-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          {m.project_switcher_all()}
        </div>
        {#if all.length === 0}
          <p class="px-2 py-3 text-center text-sm text-muted-foreground">{m.project_switcher_empty()}</p>
        {:else}
          {#each all as p (p.id)}
            {@render row(p)}
          {/each}
        {/if}
      {/if}
    </div>

    <div class="border-t border-sidebar-border p-1.5">
      <button
        type="button"
        onclick={createNew}
        class="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium text-debt-code transition-colors hover:bg-accent/50"
      >
        <Plus class="size-4" />
        <span>{m.project_switcher_new()}</span>
      </button>
    </div>
  </Popover.Content>
</Popover.Root>

{#snippet row(p: Project)}
  <button
    type="button"
    onclick={() => navigateTo(p.slug)}
    aria-current={p.id === current?.id ? "true" : undefined}
    class={cn(
      "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left transition-colors hover:bg-accent/50",
      p.id === current?.id && "bg-accent",
    )}
  >
    <FolderGit2 class="size-4 shrink-0 text-muted-foreground" />
    <span class="min-w-0 flex-1">
      <span class="block truncate text-sm">{p.name}</span>
      <span class="block truncate font-mono text-[11px] text-muted-foreground">{p.repo_full_name}</span>
    </span>
    {#if p.repo_private}
      <Lock class="size-3 shrink-0 text-muted-foreground" />
    {/if}
  </button>
{/snippet}
