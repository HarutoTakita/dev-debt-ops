<script lang="ts">
  import { resolve } from "$app/paths";
  import type { DebtItem } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import PriorityBadge from "./priority-badge.svelte";
  import KcGauge from "./kc-gauge.svelte";
  import DeveloperAvatar from "./developer-avatar.svelte";
  import { categoryLabel, severityLabel } from "./labels";

  type Props = { orgSlug: string; projectSlug: string; debt: DebtItem };
  const { orgSlug, projectSlug, debt }: Props = $props();
</script>

<a
  href={resolve(`/${orgSlug}/${projectSlug}/matrix/${debt.id}`)}
  class="block rounded-lg border bg-card p-3 transition-colors hover:bg-accent/40"
>
  <div class="flex items-center gap-3">
    <PriorityBadge code={debt.code_debt_score} coverage={debt.knowledge_coverage} />
    <span class="min-w-0 flex-1 truncate font-mono text-sm">{debt.file_path}</span>
    <span class="shrink-0 text-xs text-muted-foreground tabular-nums">
      {m.list_estimated({ hours: debt.estimated_repay_hours })}
    </span>
  </div>
  <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 pl-0.5 text-xs">
    <KcGauge value={debt.knowledge_coverage} />
    <span class="text-muted-foreground tabular-nums"
      >{m.list_ai({ pct: Math.round(debt.ai_generation_prob * 100) })}</span
    >
    {#if debt.assigned_developers.length}
      <span class="flex items-center -space-x-1">
        {#each debt.assigned_developers as dev (dev.github_handle)}<DeveloperAvatar {dev} />{/each}
      </span>
    {/if}
    <span class="ml-auto flex items-center gap-1.5 text-muted-foreground">
      <span>{categoryLabel(debt)}</span>
      <span aria-hidden="true">·</span>
      <span>{severityLabel(debt.severity)}</span>
    </span>
  </div>
</a>
