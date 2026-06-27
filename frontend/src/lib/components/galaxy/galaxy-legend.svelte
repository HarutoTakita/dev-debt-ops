<script lang="ts">
  import type { MasteryStatus } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";
  import { masteryDot, masteryLabel } from "./galaxy-labels";

  const statuses: MasteryStatus[] = ["star", "dim_star", "black_hole", "unexplored"];
</script>

<div class="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border bg-card px-3 py-2 text-xs">
  <span class="font-medium text-foreground">{m.galaxy_legend_title()}</span>
  {#each statuses as s (s)}
    <span class="flex items-center gap-1.5 text-muted-foreground">
      <span class={cn("size-3 rounded-full", masteryDot[s])}></span>
      {masteryLabel(s)}
    </span>
  {/each}
  <span class="flex items-center gap-1.5 text-muted-foreground">
    <span class="inline-block h-px w-5 border-t border-muted-foreground/60"></span>
    {m.galaxy_legend_wormhole()}
  </span>
</div>
