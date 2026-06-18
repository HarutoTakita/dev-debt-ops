<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import { page } from "$app/state";
  import { cn } from "$lib/utils";
  import * as Collapsible from "$lib/components/ui/collapsible";
  import { isActiveRoute, type NavContext, type NavSection } from "$lib/config/nav";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import NavItem from "./nav-item.svelte";

  let { section, ctx }: { section: NavSection; ctx: NavContext } = $props();

  const hasActive = $derived(section.items.some((i) => isActiveRoute(i.route(ctx), page.url.pathname)));
  let open = $state(true);
  // 現在ルートを含むセクションは自動展開（GitLab menu_section.vue の is_active 初期展開に相当）
  $effect(() => {
    if (hasActive) open = true;
  });
</script>

{#if sidebar.collapsed || section.label === null}
  <div class="flex flex-col gap-0.5">
    {#each section.items as item (item.id)}
      <NavItem {item} {ctx} />
    {/each}
  </div>
{:else}
  <Collapsible.Root bind:open>
    <Collapsible.Trigger
      class="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase transition-colors hover:text-foreground"
    >
      <span>{section.label()}</span>
      <ChevronDown class={cn("size-3.5 transition-transform", !open && "-rotate-90")} />
    </Collapsible.Trigger>
    <Collapsible.Content class="flex flex-col gap-0.5 pt-0.5">
      {#each section.items as item (item.id)}
        <NavItem {item} {ctx} />
      {/each}
    </Collapsible.Content>
  </Collapsible.Root>
{/if}
