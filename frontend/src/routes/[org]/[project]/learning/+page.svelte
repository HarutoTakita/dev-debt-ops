<script lang="ts">
  import { untrack } from "svelte";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { getLearningPlan, patchStep } from "$lib/api/client";
  import type { LearningPlan } from "$lib/api/schemas";
  import PlanProgress from "$lib/components/learning/plan-progress.svelte";
  import ResourceList from "$lib/components/learning/resource-list.svelte";
  import KnowledgeUnitList from "$lib/components/learning/knowledge-unit-list.svelte";
  import { quiz } from "$lib/stores/quiz-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  // 機能（feature）単位の単元ハブ（issue 063）。既定は単元一覧。?planId / ?from=quiz のときは
  // その単元の学習プラン詳細を表示（クイズ結果からの遷移・ブックマーク救済）。
  let { data } = $props();
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const unitsHref = $derived(resolve(`/${orgSlug}/${projectSlug}/learning`));

  // ナビ pill（受験可能クイズ件数）を最新化。
  $effect(() => {
    if (orgSlug && projectSlug) void quiz.loadAvailable(orgSlug, projectSlug).catch(() => {});
  });

  // --- 学習プラン詳細（?planId / ?from=quiz） ---
  let plan = $state<LearningPlan | null>(untrack(() => data.plan));
  refreshOnStageComplete(["plan_learning"], () => {
    if (plan && orgSlug && projectSlug) {
      void getLearningPlan(orgSlug, projectSlug, plan.id)
        .then((p) => (plan = p))
        .catch(() => {});
    }
  });
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
  <title>{m.nav_knowledge_hub()} · Rosetta</title>
</svelte:head>

{#if plan}
  <div class="mx-auto max-w-2xl space-y-4 p-4">
    <a href={unitsHref} class="text-xs text-muted-foreground hover:text-foreground">{m.unit_back()}</a>
    <div>
      <h1 class="font-display text-xl font-semibold">{m.knowledge_tab_learning()}</h1>
      {#if data.from === "quiz"}
        <p class="mt-0.5 text-xs text-debt-knowledge">{m.learning_from_quiz()}</p>
      {/if}
      <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>{m.learning_gap()}:</span>
        {#each Array.from(new Set(plan.gap_concepts)) as concept (concept)}
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
  <KnowledgeUnitList {orgSlug} {projectSlug} />
{/if}
