<script lang="ts">
  import { page } from "$app/state";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { allNavItems, navSections, type NavContext } from "$lib/config/nav";
  import * as m from "$lib/paraglide/messages";
  import MenuSection from "./menu-section.svelte";
  import NavItem from "./nav-item.svelte";
  import ProjectSwitcher from "./project-switcher.svelte";

  const projectSlug = $derived(page.params.project ?? "");
  const projectSelected = $derived(!!page.params.project);
  const ctx: NavContext = $derived({ orgSlug: page.params.org ?? "", projectSlug, projectSelected });
  const pinnedItems = $derived(allNavItems.filter((i) => sidebar.pinnedIds.includes(i.id)));
</script>

<Tooltip.Provider delayDuration={0}>
  <nav class="flex h-full flex-col gap-1 overflow-y-auto p-2" aria-label="primary">
    <div class="p-0.5">
      <ProjectSwitcher />
    </div>
    <div class="my-1 border-t border-sidebar-border"></div>

    {#if projectSelected}
      {#if pinnedItems.length > 0}
        <div class="flex flex-col gap-0.5">
          {#if !sidebar.collapsed}
            <div class="px-2.5 py-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              {m.nav_pinned()}
            </div>
          {/if}
          {#each pinnedItems as item (item.id)}
            <NavItem {item} {ctx} />
          {/each}
        </div>
        <div class="my-1 border-t border-sidebar-border"></div>
      {/if}
      {#each navSections as section (section.id)}
        <MenuSection {section} {ctx} />
      {/each}
    {:else if !sidebar.collapsed}
      <p class="px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">{m.project_switcher_hint()}</p>
    {/if}
  </nav>
</Tooltip.Provider>
