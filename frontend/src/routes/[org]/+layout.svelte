<script lang="ts">
  import { page } from "$app/state";
  import { afterNavigate } from "$app/navigation";
  import { cn } from "$lib/utils";
  import * as Sheet from "$lib/components/ui/sheet";
  import Topbar from "$lib/components/shell/topbar.svelte";
  import SuperSidebar from "$lib/components/shell/super-sidebar.svelte";
  import CreateProjectDialog from "$lib/components/shell/create-project-dialog.svelte";
  import KeyboardShortcuts from "$lib/components/shell/keyboard-shortcuts.svelte";
  import OnboardingTour from "$lib/components/onboarding/onboarding-tour.svelte";
  import { tourSteps, mobileTourSteps, isMobileTour } from "$lib/components/onboarding/tour-steps";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import { onboarding } from "$lib/stores/onboarding-store.svelte";

  let { children } = $props();

  // 初回プロジェクト作成 → 遷移後にツアーを一度だけ自動開始（issue 066）。
  // PC はサイドバー版（tourSteps）、モバイルはページ内コンテンツを対象にする mobileTourSteps を出す
  // （モバイルはサイドバーがドロワー内で非表示のため、専用ステップで各画面を案内する）。
  $effect(() => {
    const orgSlug = page.params.org;
    if (!orgSlug) return;
    if (onboarding.consumeAutoStart(orgSlug)) onboarding.start(isMobileTour() ? mobileTourSteps : tourSteps);
  });

  // モバイル: ドロワー内のリンクで遷移したら Sheet を閉じる（開いたまま遷移先を覆う不具合を防ぐ）。
  afterNavigate(() => {
    sidebar.mobileOpen = false;
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
        <Sheet.Title class="sr-only">DevDebtOps</Sheet.Title>
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

<CreateProjectDialog />
<KeyboardShortcuts />
<OnboardingTour />
