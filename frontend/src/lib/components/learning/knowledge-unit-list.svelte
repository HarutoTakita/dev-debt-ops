<script lang="ts">
  import { resolve } from "$app/paths";
  import { goto } from "$app/navigation";
  import type { ResolvedPathname } from "$app/types";
  import { generateBaselineQuizzes, generatePlan, getKnowledgeUnits } from "$lib/api/client";
  import type { KnowledgeUnit } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { cn } from "$lib/utils";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  // 機能（feature）単位の単元ハブ（issue 063）。各単元で 学習 → 確認クイズ → KC 更新（理解済み）を回す。
  type Props = { orgSlug: string; projectSlug: string };
  const { orgSlug, projectSlug }: Props = $props();

  let units = $state<KnowledgeUnit[]>([]);
  let loading = $state(true);
  let busyKey = $state<string | null>(null); // プラン生成中の単元
  let preparing = $state(false); // 確認クイズ一括用意中

  async function load() {
    loading = true;
    try {
      units = await getKnowledgeUnits(orgSlug, projectSlug);
    } catch {
      units = [];
    } finally {
      loading = false;
    }
  }
  $effect(() => {
    void orgSlug;
    void projectSlug;
    void load();
  });
  // 解析・採点・プラン生成の完了で単元を再取得（issue 049）。
  refreshOnStageComplete(["analyze_galaxy", "plan_learning"], load);

  function kcPct(kc: number): number {
    return Math.round(Math.max(0, Math.min(1, kc)) * 100);
  }
  const STATUS: Record<string, { label: () => string; tone: string }> = {
    unstarted: { label: m.unit_status_unstarted, tone: "text-muted-foreground" },
    in_progress: { label: m.unit_status_in_progress, tone: "text-debt-knowledge" },
    verified: { label: m.unit_status_verified, tone: "text-success" },
    needs_review: { label: m.unit_status_needs_review, tone: "text-destructive" },
  };
  function statusOf(s: string) {
    return STATUS[s] ?? STATUS.unstarted;
  }

  async function createPlan(u: KnowledgeUnit) {
    busyKey = u.feature_key;
    try {
      const { plan_id } = await generatePlan(orgSlug, projectSlug, { featureId: u.feature_id });
      const href = (resolve(`/${orgSlug}/${projectSlug}/learning`) + `?planId=${plan_id}`) as ResolvedPathname;
      await goto(href);
    } catch {
      /* surface nothing; the button re-enables */
    } finally {
      busyKey = null;
    }
  }
  async function prepareQuizzes() {
    preparing = true;
    try {
      await generateBaselineQuizzes(orgSlug, projectSlug);
      await load();
    } catch {
      /* keep */
    } finally {
      preparing = false;
    }
  }

  const anyQuizMissing = $derived(units.some((u) => !u.quiz_session_id));
</script>

<div class="mx-auto max-w-2xl space-y-4 p-4">
  <div class="flex items-baseline justify-between gap-2">
    <h1 class="font-display text-xl font-semibold">{m.units_title()}</h1>
    {#if units.length > 0 && anyQuizMissing}
      <Button variant="outline" size="sm" class="h-7 px-2 text-xs" disabled={preparing} onclick={prepareQuizzes}>
        {m.unit_prepare_quizzes()}
      </Button>
    {/if}
  </div>
  <p class="text-xs text-muted-foreground">{m.units_subtitle()}</p>

  {#if loading}
    <p class="py-8 text-center text-sm text-muted-foreground">…</p>
  {:else if units.length === 0}
    <p class="py-8 text-center text-sm text-muted-foreground">{m.units_empty()}</p>
  {:else}
    <ul class="flex flex-col gap-2">
      {#each units as u (u.feature_key)}
        <li class="rounded-lg border bg-card p-3">
          <div class="flex items-center gap-3">
            <span class="min-w-0 flex-1 truncate font-medium">{u.name}</span>
            <span class={cn("shrink-0 text-xs font-medium", statusOf(u.status).tone)}
              >{statusOf(u.status).label()}</span
            >
            <span class="shrink-0 text-xs text-muted-foreground">KC {kcPct(u.knowledge_coverage)}%</span>
            <span class="shrink-0 text-xs text-muted-foreground">{m.unit_files_count({ count: u.file_count })}</span>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            {#if u.learning_plan_id}
              <a
                href={(resolve(`/${orgSlug}/${projectSlug}/learning`) +
                  `?planId=${u.learning_plan_id}`) as ResolvedPathname}
                class="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40"
              >
                {m.unit_learn_open()}
              </a>
            {:else}
              <Button
                variant="outline"
                size="sm"
                class="h-7 px-2.5 text-xs"
                disabled={busyKey === u.feature_key}
                onclick={() => createPlan(u)}
              >
                {m.unit_learn_create()}
              </Button>
            {/if}
            {#if u.quiz_session_id}
              <a
                href={resolve(`/${orgSlug}/${projectSlug}/quizzes/${u.quiz_session_id}`)}
                class="rounded-md border px-2.5 py-1 text-xs font-medium text-debt-knowledge hover:bg-accent/40"
              >
                {m.unit_confirm()}
              </a>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>
