<script lang="ts">
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { project } from "$lib/stores/project-store.svelte";
  import * as m from "$lib/paraglide/messages";
  import ProjectSwitcher from "./project-switcher.svelte";
  import ProjectNavGroup from "./project-nav-group.svelte";

  const orgSlug = $derived(page.params.org ?? "");
  const currentId = $derived(project.current?.id);

  // サイドバーはプロジェクト単位の開閉グループ。org の全プロジェクトを同時に並べ、各自のメニューを開閉する。
  // 一覧未取得（直リンク到達など）でも現在プロジェクトのメニューは即使えるよう、フォールバックで current を出す。
  const projects = $derived(project.list.length > 0 ? project.list : project.current ? [project.current] : []);

  // org が変わったら一覧をロードする（スイッチャー Popover を開かなくてもサイドバーに全件出すため）。
  // loadList の戻り（list/loading）は読まず org のみ追跡し、自分の書き込みでの再実行ループを避ける。
  let loadedOrg: string | null = null;
  $effect(() => {
    const org = page.params.org ?? "";
    if (org && org !== loadedOrg) {
      loadedOrg = org;
      project.loadList(org);
    }
  });

  const skeletonRows = Array.from({ length: 4 }, (_v, i) => i);
</script>

<Tooltip.Provider delayDuration={0}>
  <nav class="flex h-full flex-col gap-1 overflow-y-auto p-2" aria-label="primary">
    <div class="p-0.5">
      <ProjectSwitcher />
    </div>
    <div class="my-1 border-t border-sidebar-border"></div>

    {#if !sidebar.collapsed}
      <div class="px-2.5 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {m.nav_projects()}
      </div>
    {/if}

    {#if projects.length > 0}
      {#if sidebar.collapsed}
        <!-- 折りたたみ時はサブメニューを畳めないため、各プロジェクトの Overview へのアイコンリンクにする。 -->
        <div class="flex flex-col gap-0.5">
          {#each projects as p (p.id)}
            <Tooltip.Root>
              <Tooltip.Trigger>
                {#snippet child({ props })}
                  <a
                    {...props}
                    href={resolve(`/${orgSlug}/${p.slug}`)}
                    aria-current={p.id === currentId ? "page" : undefined}
                    class={cn(
                      "flex h-9 items-center justify-center rounded-md transition-colors",
                      p.id === currentId
                        ? "bg-accent text-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                  >
                    <FolderGit2 class="size-4" />
                  </a>
                {/snippet}
              </Tooltip.Trigger>
              <Tooltip.Content side="right">{p.name}</Tooltip.Content>
            </Tooltip.Root>
          {/each}
        </div>
      {:else}
        <div class="flex flex-col gap-0.5">
          {#each projects as p (p.id)}
            <ProjectNavGroup project={p} {orgSlug} active={p.id === currentId} />
          {/each}
        </div>
      {/if}
    {:else if project.loading}
      <div class="flex flex-col gap-1 px-1" aria-busy="true">
        {#each skeletonRows as i (i)}
          <div class="flex items-center gap-2 px-1.5 py-1.5">
            <Skeleton class="size-5 rounded" />
            {#if !sidebar.collapsed}<Skeleton class="h-4 flex-1" />{/if}
          </div>
        {/each}
      </div>
    {:else if project.error !== null && !sidebar.collapsed}
      <div class="flex flex-col items-start gap-2 px-2.5 py-2">
        <p class="text-xs text-destructive">{m.project_switcher_error()}</p>
        <button
          type="button"
          onclick={() => project.loadList(orgSlug)}
          class="rounded-md border px-2.5 py-1 text-xs hover:bg-accent/50"
        >
          {m.common_retry()}
        </button>
      </div>
    {:else if !sidebar.collapsed}
      <p class="px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">{m.project_switcher_hint()}</p>
    {/if}
  </nav>
</Tooltip.Provider>
