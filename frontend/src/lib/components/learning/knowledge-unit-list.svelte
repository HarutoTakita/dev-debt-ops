<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import { getKnowledgeUnits } from "$lib/api/client";
  import type { KnowledgeUnit } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  // 機能（feature）単位の単元ハブ（issue 063）。各単元で 学習 → 確認クイズ → KC 更新（理解済み）を回す。
  type Props = { orgSlug: string; projectSlug: string };
  const { orgSlug, projectSlug }: Props = $props();

  let units = $state<KnowledgeUnit[]>([]);
  let loading = $state(true);

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
  // 機能クラスタリング・理解度分析・プラン生成の完了で単元を再取得（issue 049）。
  refreshOnStageComplete(["cluster_features", "analyze_galaxy", "plan_learning"], load);

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
</script>

<div class="mx-auto max-w-2xl space-y-4 p-4" data-tour="units-list">
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
                data-tour="unit-learn"
                class="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40"
              >
                {m.unit_learn_open()}
              </a>
            {:else}
              <span class="text-xs text-muted-foreground">{m.unit_pending()}</span>
            {/if}
            {#if u.quiz_session_id}
              <a
                href={resolve(`/${orgSlug}/${projectSlug}/quizzes/${u.quiz_session_id}`)}
                data-tour="unit-confirm"
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
