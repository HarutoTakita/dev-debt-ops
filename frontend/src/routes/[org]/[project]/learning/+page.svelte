<script lang="ts">
  import { untrack } from "svelte";
  import { resolve } from "$app/paths";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import type { ResolvedPathname } from "$app/types";
  import { getLearningPlan, patchStep } from "$lib/api/client";
  import type { LearningPlan } from "$lib/api/schemas";
  import * as Tabs from "$lib/components/ui/tabs";
  import { Button } from "$lib/components/ui/button";
  import CommonComingSoon from "$lib/components/common/coming-soon-placeholder.svelte";
  import QuizComingSoon from "$lib/components/quiz/coming-soon-placeholder.svelte";
  import QuizList from "$lib/components/quiz/quiz-list.svelte";
  import PlanProgress from "$lib/components/learning/plan-progress.svelte";
  import ResourceList from "$lib/components/learning/resource-list.svelte";
  import { quiz } from "$lib/stores/quiz-store.svelte";
  import { analysisRun } from "$lib/stores/analysis-run-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  // クイズ（実測）と学習（返済）を 1 画面のタブに統合したハブ（理解負債ループの両輪）。
  let { data } = $props();
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // タブ初期値: ?tab=quiz|learning を優先。無ければ plan/from=quiz があれば学習、それ以外はクイズ（実測が起点）。
  let tab = $state<string>(
    untrack(() => page.url.searchParams.get("tab") ?? (data.from === "quiz" || data.plan ? "learning" : "quiz")),
  );

  // --- クイズ（実測） ---
  function loadAvailable() {
    if (orgSlug && projectSlug) void quiz.loadAvailable(orgSlug, projectSlug).catch(() => {});
  }
  $effect(() => {
    void orgSlug;
    void projectSlug;
    loadAvailable();
  });
  // 返済ループ完了で受験可能クイズを自動リフレッシュ（issue 049）。
  refreshOnStageComplete(["loop_agents"], loadAvailable);

  // --- 学習（返済） ---
  let preview = $state(untrack(() => data.from === "quiz"));
  let plan = $state<LearningPlan | null>(untrack(() => data.plan));
  let generating = $state(false);
  function generatePlanNow() {
    generating = true;
    void analysisRun.runStage("plan_learning", { orgSlug, projectSlug, owner: "", repo: "" });
  }
  $effect(() => {
    const st = analysisRun.stages.plan_learning;
    if (generating && st.status === "COMPLETED" && st.link) {
      generating = false;
      void goto(st.link as ResolvedPathname);
    } else if (generating && st.status === "FAILED") {
      generating = false;
    }
  });
  // 既存プラン表示中にコックピットでプラン生成が完了したら、その場で再取得して反映（issue 049）。
  refreshOnStageComplete(["plan_learning"], () => {
    if (!generating && plan && orgSlug && projectSlug) {
      void getLearningPlan(orgSlug, projectSlug, plan.id)
        .then((p) => (plan = p))
        .catch(() => {});
    }
  });
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
  <title>{m.nav_knowledge_hub()} · Rosetta</title>
</svelte:head>

<div class="mx-auto flex h-full max-w-2xl flex-col gap-4 p-4">
  <Tabs.Root bind:value={tab} class="flex min-h-0 flex-1 flex-col">
    <Tabs.List>
      <Tabs.Trigger value="quiz">
        {m.knowledge_tab_quiz()}{#if quiz.availableCount > 0}（{quiz.availableCount}）{/if}
      </Tabs.Trigger>
      <Tabs.Trigger value="learning">{m.knowledge_tab_learning()}</Tabs.Trigger>
    </Tabs.List>

    <!-- クイズ（実測）: 低 KC ファイル/機能の理解度を出題で測る -->
    <Tabs.Content value="quiz" class="mt-3 min-h-0 flex-1">
      {#if quiz.availableCount === 0}
        <QuizComingSoon eyebrow="Re:Pay" title={m.quiz_coming_title()} description={m.quiz_coming_desc()}>
          {#snippet action()}
            <Button onclick={() => quiz.loadAvailable(orgSlug, projectSlug)}>{m.quiz_coming_demo()}</Button>
          {/snippet}
        </QuizComingSoon>
      {:else}
        <div class="space-y-3">
          <p class="text-xs text-muted-foreground">{m.quiz_list_subtitle()}</p>
          <QuizList quizzes={quiz.quizzes} {orgSlug} {projectSlug} />
        </div>
      {/if}
    </Tabs.Content>

    <!-- 学習（返済）: チーム資産 + 外部資料で理解ギャップを埋める -->
    <Tabs.Content value="learning" class="mt-3 min-h-0 flex-1">
      {#if preview && plan}
        <div class="space-y-4">
          {#if data.from === "quiz"}
            <p class="text-xs text-debt-knowledge">{m.learning_from_quiz()}</p>
          {/if}
          <div class="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
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
          <PlanProgress {plan} />
          <ResourceList steps={plan.steps} ontoggle={toggle} />
          <!-- 学習（input）→ クイズ（output）の導線。読んだら腕試しで KC を上げる（同画面タブ切替）。 -->
          <div class="border-t pt-3">
            <button
              type="button"
              onclick={() => (tab = "quiz")}
              class="inline-flex items-center gap-1.5 text-sm font-medium text-debt-knowledge underline-offset-2 hover:underline"
            >
              {m.learning_to_quiz()} →
            </button>
          </div>
        </div>
      {:else}
        <div class="flex h-full flex-col">
          <div class="flex-1">
            <CommonComingSoon title={m.learning_coming_title()} description={m.learning_coming_body()} />
          </div>
          <div class="shrink-0 space-y-3 pb-8 text-center">
            <Button disabled={generating} onclick={generatePlanNow}>
              {generating ? m.analysis_run_running() : m.learning_generate_cta()}
            </Button>
            {#if !preview}
              <div>
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
        </div>
      {/if}
    </Tabs.Content>
  </Tabs.Root>
</div>
