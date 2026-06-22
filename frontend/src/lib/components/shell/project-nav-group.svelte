<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import { page } from "$app/state";
  import { cn } from "$lib/utils";
  import * as Collapsible from "$lib/components/ui/collapsible";
  import { allNavItems, type NavContext } from "$lib/config/nav";
  import type { Project } from "$lib/api/schemas";
  import NavItem from "./nav-item.svelte";

  // プロジェクト 1 件分の開閉メニュー。トリガー（プロジェクト名）クリックで配下メニューを開閉する。
  // セクション見出し（理解する/知識負債/参照）は廃止し、本グループがプロジェクト単位の主語になる。
  let { project, orgSlug, active }: { project: Project; orgSlug: string; active: boolean } = $props();

  const ctx: NavContext = $derived({ orgSlug, projectSlug: project.slug, projectSelected: true });

  // アクティブ（選択中）プロジェクトは展開、それ以外は折りたたみで開始。マウント時およびナビゲーションで
  // アクティブが切り替わったら追従して展開する（menu_section の is_active 初期展開に相当）。手動で閉じても
  // active が変わらない限り再展開しない。
  let open = $state(false);
  $effect(() => {
    if (active) open = true;
  });
</script>

<Collapsible.Root bind:open>
  <Collapsible.Trigger
    class={cn(
      "flex h-9 w-full items-center gap-2 rounded-md px-2.5 text-left text-sm transition-colors hover:bg-accent/50",
      active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
    )}
    aria-current={active && page.url.pathname === `/${orgSlug}/${project.slug}` ? "true" : undefined}
  >
    <span
      class={cn(
        "flex size-6 shrink-0 items-center justify-center rounded",
        active ? "bg-debt-knowledge/15 text-debt-knowledge" : "text-muted-foreground",
      )}
    >
      <FolderGit2 class="size-4" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="block truncate">{project.name}</span>
    </span>
    <ChevronDown class={cn("size-4 shrink-0 transition-transform", !open && "-rotate-90")} />
  </Collapsible.Trigger>
  <Collapsible.Content class="flex flex-col gap-0.5 py-0.5 pl-3.5">
    {#each allNavItems as item (item.id)}
      <NavItem {item} {ctx} showPill={active} />
    {/each}
  </Collapsible.Content>
</Collapsible.Root>
