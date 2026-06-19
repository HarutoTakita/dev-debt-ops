<script lang="ts">
  import type { LearningStep } from "$lib/api/schemas";
  import ResourceCard from "./resource-card.svelte";
  import * as m from "$lib/paraglide/messages";

  // 段階 1: チーム内資産（最優先で上）/ 段階 2: 外部資源候補（二次）。
  type Props = { steps: LearningStep[]; ontoggle?: (order: number, completed: boolean) => void };
  const { steps, ontoggle }: Props = $props();

  const teamSteps = $derived(steps.filter((s) => s.resource.origin === "team").sort((a, b) => a.order - b.order));
  const externalSteps = $derived(
    steps.filter((s) => s.resource.origin === "external").sort((a, b) => a.order - b.order),
  );
</script>

<div class="space-y-5">
  <section>
    <h3 class="font-display text-sm font-semibold text-debt-knowledge">★ {m.learning_team_heading()}</h3>
    <div class="mt-2 space-y-2">
      {#each teamSteps as s (s.order)}
        <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
      {/each}
    </div>
  </section>

  {#if externalSteps.length > 0}
    <section>
      <h3 class="text-sm font-medium text-muted-foreground">{m.learning_external_heading()}</h3>
      <div class="mt-2 space-y-2">
        {#each externalSteps as s (s.order)}
          <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
        {/each}
      </div>
    </section>
  {/if}
</div>
