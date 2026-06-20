<script lang="ts">
  import { untrack } from "svelte";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { patchStep } from "$lib/api/client";
  import type { LearningPlan } from "$lib/api/schemas";
  import ComingSoonPlaceholder from "$lib/components/common/coming-soon-placeholder.svelte";
  import PlanProgress from "$lib/components/learning/plan-progress.svelte";
  import ResourceList from "$lib/components/learning/resource-list.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  // クイズ結果 CTA 経由（?from=quiz / ?planId）でプランがあれば本体を表示。無ければ Coming Soon。
  let preview = $state(untrack(() => data.from === "quiz"));
  let plan = $state<LearningPlan | null>(untrack(() => data.plan));

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // ステップ完了の楽観更新（PATCH 実 API。失敗時は据え置き）。
  async function toggle(order: number, completed: boolean) {
    if (!plan) return;
    try {
      await patchStep(orgSlug, projectSlug, plan.id, order, completed);
      plan = { ...plan, steps: plan.steps.map((s) => (s.order === order ? { ...s, completed } : s)) };
    } catch {
      /* keep previous state on failure */
    }
  }
</script>

<svelte:head>
  <title>{m.nav_learning()} · Rosetta</title>
</svelte:head>

{#if preview && plan}
  <div class="mx-auto max-w-2xl space-y-4 p-4">
    <div>
      <h1 class="font-display text-xl font-semibold">{m.nav_learning()}</h1>
      {#if data.from === "quiz"}
        <p class="mt-0.5 text-xs text-debt-knowledge">{m.learning_from_quiz()}</p>
      {/if}
      <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>{m.learning_gap()}:</span>
        {#each plan.gap_concepts as concept (concept)}
          <a
            href={resolve(`/${orgSlug}/${projectSlug}/galaxy`)}
            title={m.gap_concept_learn({ concept })}
            aria-label={m.gap_concept_learn({ concept })}
            class="inline-flex items-center rounded-full border bg-card px-2 py-0.5 font-medium text-foreground transition-colors hover:bg-accent/40"
          >
            {concept}
          </a>
        {/each}
      </div>
    </div>
    <PlanProgress {plan} />
    <ResourceList steps={plan.steps} ontoggle={toggle} />
  </div>
{:else}
  <div class="flex h-full flex-col">
    <div class="flex-1">
      <ComingSoonPlaceholder title={m.learning_coming_title()} description={m.learning_coming_body()} />
    </div>
    {#if !preview}
      <div class="shrink-0 pb-8 text-center">
        <button
          type="button"
          onclick={() => (preview = true)}
          class="text-xs text-muted-foreground underline hover:text-foreground"
        >
          {m.learning_preview()}
        </button>
      </div>
    {/if}
  </div>
{/if}
