<script lang="ts">
  import type { ResolvedPathname } from "$app/types";
  import { Button } from "$lib/components/ui/button";
  import {
    analysisRun,
    STAGES,
    STAGE_GROUPS,
    type RunContext,
    type StageGroupDef,
    type StageStatus,
  } from "$lib/stores/analysis-run-store.svelte";
  import { auth } from "$lib/stores/auth.svelte";
  import * as m from "$lib/paraglide/messages";

  // 解析は GitHub リポジトリの読み取りを伴うため、ゲストデモでは実行不可（issue 069）。
  const demoBlockMain = "デモでは解析を実行できません";
  const demoBlockHint = "（GitHub サインインが必要です）";
  const demoBlockTitle = `${demoBlockMain}${demoBlockHint}`;

  // 解析ラン・コックピット。生成導線は単一の主 CTA に集約（issue 064）。表示は「検知 / 計測 / 用意」の
  // 3 グループに集約し、各グループは内部ステージ（裏のジョブ）の集約状態と実行中サブステップを示す。
  type Props = { ctx: RunContext };
  const { ctx }: Props = $props();

  const groupLabel: Record<string, () => string> = {
    analysis_group_technical: m.analysis_group_technical,
    analysis_group_knowledge: m.analysis_group_knowledge,
    analysis_group_repay: m.analysis_group_repay,
  };
  // グループ内で実行中のサブステップ名を出すためのステージラベル。
  const stageLabel: Record<string, () => string> = {
    analysis_stage_detect_code: m.analysis_stage_detect_code,
    analysis_stage_detect_knowledge: m.analysis_stage_detect_knowledge,
    analysis_stage_analyze_galaxy: m.analysis_stage_analyze_galaxy,
    analysis_stage_cluster_features: m.analysis_stage_cluster_features,
    analysis_stage_plan_learning: m.analysis_stage_plan_learning,
    analysis_stage_confirm_quizzes: m.analysis_stage_confirm_quizzes,
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

  // グループの集約状態と、実行中サブステージのラベルを内部ステージ群から導出する。
  function groupView(g: StageGroupDef): { status: StageStatus; activeLabel: string | null } {
    const members = g.stageIds.map((id) => analysisRun.stages[id]).filter(Boolean);
    if (members.some((s) => s.status === "FAILED")) return { status: "FAILED", activeLabel: null };
    const activeId = g.stageIds.find((id) => {
      const s = analysisRun.stages[id];
      return s && (s.status === "QUEUED" || s.status === "PROCESSING");
    });
    if (activeId) {
      const def = STAGES.find((s) => s.id === activeId);
      return { status: "PROCESSING", activeLabel: def ? stageLabel[def.labelKey]() : null };
    }
    if (members.length > 0 && members.every((s) => s.status === "COMPLETED")) {
      return { status: "COMPLETED", activeLabel: null };
    }
    if (members.some((s) => s.status !== "idle")) return { status: "PROCESSING", activeLabel: null };
    return { status: "idle", activeLabel: null };
  }

  function retryGroup(g: StageGroupDef) {
    for (const id of g.stageIds) {
      if (analysisRun.stages[id]?.status === "FAILED") void analysisRun.runStage(id, ctx);
    }
  }

  // 注意: analysisRun は複数ページが共有するシングルトン。cockpit unmount で cancel() すると
  // 他ページが起動したポーリングまで止めてしまうため、ここでは cancel しない（issue-044）。
  // リロード後の状態復元: 永続化済みジョブからステージ状態を復元（プロジェクトごとに一度だけ）。
  $effect(() => {
    if (ctx.orgSlug && ctx.projectSlug) void analysisRun.hydrate(ctx);
  });
</script>

<section class="w-full">
  {#if !analysisRun.started}
    <div class="flex flex-col items-start gap-2 rounded-lg border bg-card p-4">
      <h2 class="font-display text-sm font-semibold">{m.analysis_run_title()}</h2>
      <Button
        disabled={analysisRun.running || auth.isDemo}
        title={auth.isDemo ? demoBlockTitle : undefined}
        onclick={() => analysisRun.runAll(ctx)}>{m.analysis_run_cta()}</Button
      >
      {#if auth.isDemo}
        <p class="text-xs leading-snug text-muted-foreground">
          {demoBlockMain}<br />{demoBlockHint}
        </p>
      {/if}
    </div>
  {:else}
    <div class="rounded-lg border bg-card p-4">
      <div class="mb-3 flex items-center justify-between gap-2">
        <h2 class="font-display text-sm font-semibold">{m.analysis_run_title()}</h2>
        <div class="flex items-center gap-2">
          {#if analysisRun.running}
            <Button variant="outline" size="sm" class="h-7 px-2 text-xs" onclick={() => analysisRun.cancelRun(ctx)}>
              {m.common_cancel()}
            </Button>
          {/if}
          <Button
            variant="outline"
            size="sm"
            class="h-7 px-2 text-xs"
            disabled={analysisRun.running || auth.isDemo}
            title={auth.isDemo ? demoBlockTitle : undefined}
            onclick={() => analysisRun.runAll(ctx)}
          >
            {analysisRun.running ? m.analysis_run_running() : m.analysis_regenerate()}
          </Button>
        </div>
      </div>
      <ul class="flex flex-col gap-1.5">
        {#each STAGE_GROUPS as group (group.id)}
          {@const gv = groupView(group)}
          <li class="flex items-center gap-3 rounded-md border bg-background/40 px-3 py-2 text-sm">
            <span class={`w-16 shrink-0 text-xs font-medium ${statusTone[gv.status]}`}>{statusLabel(gv.status)}</span>
            <span class="min-w-0 flex-1 truncate">
              {groupLabel[group.labelKey]()}
              {#if gv.activeLabel}<span class="text-xs text-muted-foreground"> · {gv.activeLabel}</span>{/if}
            </span>
            {#if gv.status === "COMPLETED"}
              <a
                href={group.deepLink(ctx) as ResolvedPathname}
                class="shrink-0 text-xs font-medium text-debt-knowledge underline hover:text-foreground"
              >
                {m.analysis_view()}
              </a>
            {:else if gv.status === "FAILED"}
              <button
                type="button"
                onclick={() => retryGroup(group)}
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
