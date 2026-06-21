<script lang="ts">
  import type { MasteryStatus } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";
  import { masteryDot, masteryLabel } from "./galaxy-labels";

  const statuses: MasteryStatus[] = ["star", "dim_star", "black_hole", "unexplored"];
</script>

<div
  class="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-cyan-500/15 bg-slate-900/50 px-3 py-2 text-xs"
>
  <span class="font-medium text-cyan-200/80">{m.galaxy_legend_title()}</span>
  {#each statuses as s (s)}
    <span class="flex items-center gap-1.5 text-slate-300">
      <span class={cn("size-3 rounded-full", masteryDot[s])}></span>
      {masteryLabel(s)}
    </span>
  {/each}
  <span class="flex items-center gap-1.5 text-slate-300">
    <span class="inline-block h-px w-5 border-t border-dashed border-cyan-400/60"></span>
    {m.galaxy_legend_wormhole()}
  </span>
  <span class="flex items-center gap-1.5 text-slate-300">
    <span class="inline-block size-3 rounded-full border border-cyan-400/50"></span>
    {m.galaxy_legend_degree()}
  </span>
</div>
