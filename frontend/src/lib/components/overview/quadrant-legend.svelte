<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  type Props = { orgSlug: string; projectSlug: string };
  const { orgSlug, projectSlug }: Props = $props();

  const matrixHref = $derived(resolve(`/${orgSlug}/${projectSlug}/matrix`));

  // 4 象限の名前と一行の物語。最危険を先頭に置き視線を誘導する。href は /matrix?cell= の入口。
  const items = $derived<{ name: string; story: string; dot: string; href: ResolvedPathname }[]>([
    {
      name: m.overview_quadrant_danger(),
      story: m.overview_quadrant_danger_story(),
      dot: "bg-destructive",
      href: `${matrixHref}?cell=danger` as ResolvedPathname,
    },
    {
      name: m.overview_quadrant_code_repay(),
      story: m.overview_quadrant_code_repay_story(),
      dot: "bg-debt-knowledge",
      href: `${matrixHref}?cell=code_repay` as ResolvedPathname,
    },
    {
      name: m.overview_quadrant_refactor(),
      story: m.overview_quadrant_refactor_story(),
      dot: "bg-debt-code",
      href: `${matrixHref}?cell=refactor` as ResolvedPathname,
    },
    {
      name: m.overview_quadrant_ideal(),
      story: m.overview_quadrant_ideal_story(),
      dot: "bg-success",
      href: `${matrixHref}?cell=ideal` as ResolvedPathname,
    },
  ]);
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="text-xs font-medium text-muted-foreground">{m.overview_legend_title()}</div>
  <ul class="mt-2 space-y-2">
    {#each items as it (it.name)}
      <li>
        <a
          href={it.href}
          class="flex items-start gap-2 rounded px-1 py-0.5 text-xs transition-colors hover:bg-accent/40"
        >
          <span class={cn("mt-1 size-2 shrink-0 rounded-full", it.dot)}></span>
          <span>
            <span class="font-medium text-foreground">{it.name}</span>
            <span class="text-muted-foreground"> — {it.story}</span>
          </span>
        </a>
      </li>
    {/each}
  </ul>
</div>
