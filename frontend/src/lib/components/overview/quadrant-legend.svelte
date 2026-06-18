<script lang="ts">
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 4 象限の名前と一行の物語。最危険を先頭に置き視線を誘導する。
  const items = [
    { name: m.overview_quadrant_danger(), story: m.overview_quadrant_danger_story(), dot: "bg-destructive" },
    {
      name: m.overview_quadrant_code_repay(),
      story: m.overview_quadrant_code_repay_story(),
      dot: "bg-debt-knowledge",
    },
    { name: m.overview_quadrant_refactor(), story: m.overview_quadrant_refactor_story(), dot: "bg-debt-code" },
    { name: m.overview_quadrant_ideal(), story: m.overview_quadrant_ideal_story(), dot: "bg-success" },
  ];
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="text-xs font-medium text-muted-foreground">{m.overview_legend_title()}</div>
  <ul class="mt-2 space-y-2">
    {#each items as it (it.name)}
      <li class="flex items-start gap-2 text-xs">
        <span class={cn("mt-1 size-2 shrink-0 rounded-full", it.dot)}></span>
        <span>
          <span class="font-medium text-foreground">{it.name}</span>
          <span class="text-muted-foreground"> — {it.story}</span>
        </span>
      </li>
    {/each}
  </ul>
</div>
