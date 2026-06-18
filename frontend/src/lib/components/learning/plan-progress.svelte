<script lang="ts">
  import type { LearningPlan } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 進捗トラッキング表示の枠（永続化は未配線 = Coming Soon）。
  type Props = { plan: LearningPlan };
  const { plan }: Props = $props();

  const total = $derived(plan.steps.length);
  const done = $derived(plan.steps.filter((s) => s.completed).length);
  const remaining = $derived(
    plan.steps.filter((s) => !s.completed).reduce((acc, s) => acc + (s.resource.estimated_minutes ?? 0), 0),
  );
  const pct = $derived(total ? Math.round((done / total) * 100) : 0);
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="flex items-center justify-between gap-2 text-sm">
    <span class="font-medium">{m.learning_progress()}</span>
    <span class="rounded-full border px-1.5 py-0.5 text-[10px] tracking-wide text-muted-foreground uppercase">
      {m.coming_soon_badge()}
    </span>
  </div>
  <div class="mt-2 h-2 overflow-hidden rounded-full bg-muted">
    <div class="h-full rounded-full bg-debt-knowledge" style="width: {pct}%"></div>
  </div>
  <p class="mt-1.5 text-xs text-muted-foreground tabular-nums">
    {m.learning_progress_steps({ done, total })} · {m.learning_progress_remaining({ min: remaining })}
  </p>
</div>
