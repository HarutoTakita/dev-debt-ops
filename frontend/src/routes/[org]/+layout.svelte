<script lang="ts">
  import { cn } from "$lib/utils";
  import * as Sheet from "$lib/components/ui/sheet";
  import Topbar from "$lib/components/shell/topbar.svelte";
  import SuperSidebar from "$lib/components/shell/super-sidebar.svelte";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";

  let { children } = $props();
</script>

<div class="flex h-screen flex-col">
  <Topbar />

  <div class="flex min-h-0 flex-1">
    <!-- デスクトップ: 固定サイドバー。トグルでアイコンのみ（w-16）に折りたたむ -->
    <aside
      class={cn(
        "hidden shrink-0 border-r border-sidebar-border bg-surface-sunken transition-[width] duration-200 md:block",
        sidebar.collapsed ? "w-16" : "w-64",
      )}
    >
      <SuperSidebar />
    </aside>

    <!-- モバイル: Sheet によるオーバーレイ表示 -->
    <Sheet.Root bind:open={sidebar.mobileOpen}>
      <Sheet.Content side="left" class="w-72 bg-surface-sunken p-0">
        <Sheet.Title class="sr-only">Rosetta</Sheet.Title>
        <SuperSidebar />
      </Sheet.Content>
    </Sheet.Root>

    <main class="min-w-0 flex-1 overflow-hidden">
      {@render children()}
    </main>
  </div>
</div>
