<script lang="ts">
  import type { ResolvedPathname } from "$app/types";
  import { Button } from "$lib/components/ui/button";
  import { analysisRun, STAGES, type RunContext, type StageStatus } from "$lib/stores/analysis-run-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // 解析ラン・コックピット（issue 037）: 単一の主 CTA でコアループを段階起動し、各ステージの状態と
  // 完了ステージの deep-link を提示する。状態は共有 analysis-run-store。
  type Props = { ctx: RunContext };
  const { ctx }: Props = $props();

  const stageLabel: Record<string, () => string> = {
    analysis_stage_detect_code: m.analysis_stage_detect_code,
    analysis_stage_detect_knowledge: m.analysis_stage_detect_knowledge,
    analysis_stage_analyze_galaxy: m.analysis_stage_analyze_galaxy,
    analysis_stage_plan_learning: m.analysis_stage_plan_learning,
    analysis_stage_loop_agents: m.analysis_stage_loop_agents,
  };

  function statusLabel(s: StageStatus): string {
    const map: Record<StageStatus, () => string> = {
      idle: m.analysis_status_idle,
      QUEUED: m.analysis_status_queued,
      PROCESSING: m.analysis_status_processing,
      COMPLETED: m.analysis_status_completed,
      FAILED: m.analysis_status_failed,
    };
    return map[s]();
  }

  const statusTone: Record<StageStatus, string> = {
    idle: "text-muted-foreground",
    QUEUED: "text-muted-foreground",
    PROCESSING: "text-debt-knowledge",
    COMPLETED: "text-success",
    FAILED: "text-destructive",
  };

  // 注意: analysisRun は複数ページが共有するシングルトン。cockpit unmount で cancel() すると
  // 他ページ（Matrix/Galaxy 等）が起動したポーリングまで止めてしまうため、ここでは cancel しない。
  // プロジェクト切替時のキャンセル/リセットは [org]/[project]/+layout のクリーンアップが担う（issue-044）。

  // リロード後の状態復元: 一度でも解析したプロジェクトは、永続化済みジョブからステージ状態を
  // 復元する（hydrate はプロジェクトごとに一度だけ・run 開始済みなら no-op）。
  $effect(() => {
    if (ctx.orgSlug && ctx.projectSlug) void analysisRun.hydrate(ctx);
  });
</script>

<section class="mx-auto max-w-5xl px-4 pt-4">
  {#if !analysisRun.started}
    <div class="flex flex-col items-start gap-2 rounded-lg border bg-card p-4">
      <h2 class="font-display text-sm font-semibold">{m.analysis_run_title()}</h2>
      <Button disabled={analysisRun.running} onclick={() => analysisRun.runAll(ctx)}>{m.analysis_run_cta()}</Button>
    </div>
  {:else}
    <div class="rounded-lg border bg-card p-4">
      <div class="mb-3 flex items-center justify-between gap-2">
        <h2 class="font-display text-sm font-semibold">{m.analysis_run_title()}</h2>
        <Button
          variant="outline"
          size="sm"
          class="h-7 px-2 text-xs"
          disabled={analysisRun.running}
          onclick={() => analysisRun.runAll(ctx)}
        >
          {analysisRun.running ? m.analysis_run_running() : m.analysis_regenerate()}
        </Button>
      </div>
      <ul class="flex flex-col gap-1.5">
        {#each STAGES as stage (stage.id)}
          {@const s = analysisRun.stages[stage.id]}
          <li class="flex items-center gap-3 rounded-md border bg-background/40 px-3 py-2 text-sm">
            <span class={`w-16 shrink-0 text-xs font-medium ${statusTone[s.status]}`}>{statusLabel(s.status)}</span>
            <span class="min-w-0 flex-1 truncate">
              {stageLabel[stage.labelKey]()}
              {#if s.step}<span class="text-xs text-muted-foreground"> · {s.step}</span>{/if}
            </span>
            {#if s.status === "COMPLETED" && s.link}
              <a
                href={s.link as ResolvedPathname}
                class="shrink-0 text-xs font-medium text-debt-knowledge underline hover:text-foreground"
              >
                {m.analysis_view()}
              </a>
            {:else if s.status === "FAILED"}
              <button
                type="button"
                onclick={() => analysisRun.runStage(stage.id, ctx)}
                class="shrink-0 text-xs font-medium text-destructive underline hover:text-foreground"
              >
                {m.analysis_retry_stage()}
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</section>
