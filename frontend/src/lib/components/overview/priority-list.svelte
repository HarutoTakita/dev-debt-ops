<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import type { DebtPriority, FileDebt } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  type Props = { orgSlug: string; projectSlug: string; files: FileDebt[] };
  const { orgSlug, projectSlug, files }: Props = $props();

  const dangerHref = $derived(`${resolve(`/${orgSlug}/${projectSlug}/matrix`)}?cell=danger` as ResolvedPathname);

  const order: Record<DebtPriority, number> = { P0: 0, P1: 1, P2: 2, P3: 3 };

  // P0/P1 を優先度順に上位 6 件。
  const top = $derived(
    [...files]
      .filter((f) => f.priority === "P0" || f.priority === "P1")
      .sort((a, b) => order[a.priority] - order[b.priority] || b.code_debt_score - a.code_debt_score)
      .slice(0, 6),
  );

  const badge: Record<DebtPriority, string> = {
    P0: "bg-destructive/15 text-destructive ring-1 ring-destructive/30",
    P1: "bg-debt-code/15 text-debt-code",
    P2: "bg-muted text-muted-foreground",
    P3: "bg-muted/60 text-muted-foreground",
  };
</script>

<div>
  <div class="text-sm font-medium">{m.overview_priority_title()}</div>
  <ul class="mt-3 space-y-1.5">
    {#each top as f (f.path)}
      <li>
        <a
          href={dangerHref}
          title={m.overview_open_danger_matrix()}
          aria-label={m.overview_open_danger_matrix()}
          class="flex items-center gap-2 rounded px-1 py-0.5 text-xs transition-colors hover:bg-accent/40"
        >
          <span class={cn("rounded px-1.5 py-0.5 font-medium tabular-nums", badge[f.priority])}>{f.priority}</span>
          <span class="truncate font-mono text-muted-foreground">{f.path}</span>
        </a>
      </li>
    {/each}
  </ul>
</div>
