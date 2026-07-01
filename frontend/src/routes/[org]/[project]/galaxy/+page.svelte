<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import * as Tabs from "$lib/components/ui/tabs";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import ComingSoonPlaceholder from "$lib/components/galaxy/coming-soon-placeholder.svelte";
  import StarMap from "$lib/components/galaxy/star-map.svelte";
  import GalaxyLegend from "$lib/components/galaxy/galaxy-legend.svelte";
  import MasteryList from "$lib/components/galaxy/mastery-list.svelte";
  import PageHeading from "$lib/components/shell/page-heading.svelte";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // 狭幅（<768px）では密なマップではなく list タブを既定にする（rank30）。
  let tab = $state("map");
  onMount(() => {
    if (window.matchMedia("(max-width: 767px)").matches) tab = "list";
    // 実 API から個人 KC マップを取得（未観測なら observed=false で ComingSoonPlaceholder が出る）。
    if (orgSlug && projectSlug) void galaxy.load(orgSlug, projectSlug).catch(() => galaxy.reset());
  });

  // コックピットの解析完了で自動リフレッシュ（agentic が KC/機能を生成 → galaxy.load、issue 049/069）。
  // 再取得失敗時は既存表示を保持（reset しない）。
  refreshOnStageComplete(["agentic"], () => {
    if (orgSlug && projectSlug) void galaxy.load(orgSlug, projectSlug).catch(() => {});
  });
</script>

<svelte:head>
  <title>{m.nav_galaxy()} · DevDebtOps</title>
</svelte:head>

{#if !galaxy.observed || !galaxy.galaxy}
  <ComingSoonPlaceholder />
{:else}
  <div class="mx-auto flex h-full max-w-6xl flex-col gap-3 p-4">
    <PageHeading title={m.nav_galaxy()} description={m.page_galaxy_desc()} />
    <Tabs.Root bind:value={tab} class="flex min-h-0 flex-1 flex-col">
      <div class="flex items-center justify-between gap-2">
        <Tabs.List data-tour="galaxy-views">
          <Tabs.Trigger value="map" data-tour="galaxy-tab-map">{m.galaxy_tab_map()}</Tabs.Trigger>
          <Tabs.Trigger value="list" data-tour="galaxy-tab-list">{m.galaxy_tab_list()}</Tabs.Trigger>
        </Tabs.List>
        {#if galaxy.myKc !== null}
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            {m.galaxy_my_kc()}: <span class="font-medium text-foreground">{galaxy.myKc}%</span>
          </span>
        {/if}
      </div>

      <Tabs.Content value="map" class="mt-3 flex min-h-0 flex-1 flex-col gap-3">
        <Tooltip.Provider delayDuration={150}>
          <div class="min-h-0 flex-1" data-tour="galaxy-map">
            <StarMap galaxy={galaxy.galaxy} {orgSlug} {projectSlug} />
          </div>
        </Tooltip.Provider>
        <GalaxyLegend />
      </Tabs.Content>

      <Tabs.Content value="list" class="mt-3 flex-1 overflow-auto" data-tour="galaxy-list">
        <MasteryList galaxy={galaxy.galaxy} />
      </Tabs.Content>
    </Tabs.Root>
  </div>
{/if}
