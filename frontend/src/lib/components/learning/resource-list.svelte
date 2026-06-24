<script lang="ts">
  import type { LearningStep } from "$lib/api/schemas";
  import ResourceCard from "./resource-card.svelte";
  import * as m from "$lib/paraglide/messages";

  // 2 セクション（issue 068）: code=このコードを理解する（具体）/ stack=技術スタックを学ぶ（一般）。
  type Props = { steps: LearningStep[]; ontoggle?: (order: number, completed: boolean) => void };
  const { steps, ontoggle }: Props = $props();

  const codeSteps = $derived(steps.filter((s) => s.resource.section === "code").sort((a, b) => a.order - b.order));
  const stackSteps = $derived(steps.filter((s) => s.resource.section === "stack").sort((a, b) => a.order - b.order));
</script>

<div class="space-y-5">
  {#if codeSteps.length > 0}
    <section>
      <h3 class="font-display text-sm font-semibold text-debt-knowledge">{m.learning_code_heading()}</h3>
      <div class="mt-2 space-y-2">
        {#each codeSteps as s (s.order)}
          <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
        {/each}
      </div>
    </section>
  {/if}

  {#if stackSteps.length > 0}
    <section>
      <h3 class="text-sm font-medium text-muted-foreground">{m.learning_stack_heading()}</h3>
      <div class="mt-2 space-y-2">
        {#each stackSteps as s (s.order)}
          <ResourceCard resource={s.resource} completed={s.completed} order={s.order} {ontoggle} />
        {/each}
      </div>
    </section>
  {/if}
</div>
