<script lang="ts">
  import Menu from "@lucide/svelte/icons/menu";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { Button } from "$lib/components/ui/button";
  import Logo from "$lib/components/logo.svelte";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import * as m from "$lib/paraglide/messages";
  import SuperSidebarToggle from "./super-sidebar-toggle.svelte";
  import Breadcrumbs from "./breadcrumbs.svelte";
  import CommandPaletteTrigger from "./command-palette-trigger.svelte";
  import AnalysisRunControl from "./analysis-run-control.svelte";
  import UserMenu from "./user-menu.svelte";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSelected = $derived(!!page.params.project);
</script>

<header class="flex h-14 shrink-0 items-center gap-3 border-b border-sidebar-border bg-surface-sunken px-3">
  <div class="flex items-center gap-2">
    <!-- モバイル: サイドバーをオーバーレイで開く -->
    <Button
      variant="ghost"
      size="icon-sm"
      class="md:hidden"
      onclick={() => (sidebar.mobileOpen = true)}
      aria-label={m.shell_open_menu()}
    >
      <Menu />
    </Button>
    <!-- デスクトップ: サイドバー開閉トグル -->
    <div class="hidden md:block">
      <SuperSidebarToggle />
    </div>
    <a href={resolve(`/${orgSlug}`)} class="flex items-center gap-2 text-foreground">
      <Logo class="size-5 text-debt-code" />
      <span class="font-display text-base font-semibold tracking-tight">DevDebtOps</span>
    </a>
  </div>

  <div class="mx-2 hidden min-w-0 flex-1 sm:flex">
    <Breadcrumbs />
  </div>

  <div class="ml-auto flex items-center gap-2">
    <div class="hidden sm:block">
      <CommandPaletteTrigger />
    </div>
    {#if projectSelected}
      <AnalysisRunControl />
    {/if}
    <UserMenu />
  </div>
</header>
