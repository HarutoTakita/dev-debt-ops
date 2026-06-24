<script lang="ts">
  import type { LearningPlan } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 進捗トラッキング表示の枠。
  type Props = { plan: LearningPlan };
  const { plan }: Props = $props();

  const total = $derived(plan.steps.length);
  const done = $derived(plan.steps.filter((s) => s.completed).length);
  const remaining = $derived(
    plan.steps.filter((s) => !s.completed).reduce((acc, s) => acc + (s.resource.estimated_minutes ?? 0), 0),
  );
  const complete = $derived(total > 0 && done === total);
  const pct = $derived(total ? Math.round((done / total) * 100) : 0);
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="text-sm">
    <span class="font-medium">{m.learning_progress()}</span>
  </div>
  <div class="mt-2 h-2 overflow-hidden rounded-full bg-muted">
    <div class="h-full rounded-full bg-debt-knowledge" style="width: {pct}%"></div>
  </div>
  <p class="mt-1.5 text-xs text-muted-foreground tabular-nums">
    {m.learning_progress_steps({ done, total })} · {complete
      ? m.learning_progress_done()
      : m.learning_progress_remaining({ min: remaining })}
  </p>
</div>
