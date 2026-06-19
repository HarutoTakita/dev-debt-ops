<script lang="ts">
  import * as Tabs from "$lib/components/ui/tabs";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import ComingSoonPlaceholder from "$lib/components/galaxy/coming-soon-placeholder.svelte";
  import StarMap from "$lib/components/galaxy/star-map.svelte";
  import GalaxyLegend from "$lib/components/galaxy/galaxy-legend.svelte";
  import MasteryList from "$lib/components/galaxy/mastery-list.svelte";
  import AxisLegend from "$lib/components/overview/axis-legend.svelte";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head>
  <title>Knowledge Galaxy · Rosetta</title>
</svelte:head>

{#if !galaxy.observed || !galaxy.galaxy}
  <ComingSoonPlaceholder />
{:else}
  <div class="mx-auto flex h-full max-w-5xl flex-col gap-3 p-4">
    <Tabs.Root value="map" class="flex min-h-0 flex-1 flex-col">
      <div class="flex items-center justify-between gap-2">
        <Tabs.List>
          <Tabs.Trigger value="map">{m.galaxy_tab_map()}</Tabs.Trigger>
          <Tabs.Trigger value="list">{m.galaxy_tab_list()}</Tabs.Trigger>
        </Tabs.List>
        {#if galaxy.myKc !== null}
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            {m.galaxy_my_kc()}: <span class="font-medium text-foreground">{galaxy.myKc}%</span>
            <AxisLegend />
          </span>
        {/if}
      </div>

      <Tabs.Content value="map" class="mt-3 flex min-h-0 flex-1 flex-col gap-3">
        <Tooltip.Provider delayDuration={150}>
          <div class="min-h-0 flex-1"><StarMap galaxy={galaxy.galaxy} /></div>
        </Tooltip.Provider>
        <GalaxyLegend />
      </Tabs.Content>

      <Tabs.Content value="list" class="mt-3 flex-1 overflow-auto">
        <MasteryList galaxy={galaxy.galaxy} />
      </Tabs.Content>
    </Tabs.Root>
  </div>
{/if}
