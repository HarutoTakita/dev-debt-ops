<script lang="ts">
  import { page } from "$app/state";
  import { cn } from "$lib/utils";
  import * as Sheet from "$lib/components/ui/sheet";
  import Topbar from "$lib/components/shell/topbar.svelte";
  import SuperSidebar from "$lib/components/shell/super-sidebar.svelte";
  import OnboardingTour from "$lib/components/onboarding/onboarding-tour.svelte";
  import { tourSteps } from "$lib/components/onboarding/tour-steps";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";

  let { children } = $props();

  // 初回プロジェクト作成 → 遷移後にツアーを一度だけ自動開始（issue 066）。
  $effect(() => {
    const orgSlug = page.params.org;
    if (orgSlug && onboarding.consumeAutoStart(orgSlug)) onboarding.start(tourSteps);
  });
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

    <!-- メイン領域のみ縦スクロール（トップバー/サイドバーは固定）。overflow-hidden だと
         縦長ページの下部が見切れてスクロールできないため overflow-y-auto にする。 -->
    <main class="min-w-0 flex-1 overflow-y-auto">
      {@render children()}
    </main>
  </div>
</div>

<OnboardingTour />
