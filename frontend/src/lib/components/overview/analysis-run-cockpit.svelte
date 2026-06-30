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
  import type { JobProgressStep } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 解析は GitHub リポジトリの読み取りを伴うため、ゲストデモでは実行不可（issue 069）。
  const demoBlockMain = "デモでは解析を実行できません";
  const demoBlockHint = "（GitHub サインインが必要です）";
  const demoBlockTitle = `${demoBlockMain}${demoBlockHint}`;

  // 解析ラン・コックピット。生成導線は単一の主 CTA に集約（issue 064/069）。表示は「検知 / 計測 / 用意 /
  // Twin Agent」のグループに集約し、各グループは内部ステージ（裏のジョブ）の集約状態と実行中サブステップを示す。
  type Props = { ctx: RunContext };
  const { ctx }: Props = $props();

  const groupLabel: Record<string, () => string> = {
    analysis_group_technical: m.analysis_group_technical,
    analysis_group_knowledge: m.analysis_group_knowledge,
    analysis_group_repay: m.analysis_group_repay,
    analysis_group_agent: m.analysis_group_agent,
  };
  // グループ内で実行中のサブステップ名を出すためのステージラベル。
  const stageLabel: Record<string, () => string> = {
    analysis_stage_detect_code: m.analysis_stage_detect_code,
    analysis_stage_detect_knowledge: m.analysis_stage_detect_knowledge,
    analysis_stage_analyze_galaxy: m.analysis_stage_analyze_galaxy,
    analysis_stage_cluster_features: m.analysis_stage_cluster_features,
    analysis_stage_plan_learning: m.analysis_stage_plan_learning,
    analysis_stage_confirm_quizzes: m.analysis_stage_confirm_quizzes,
    analysis_stage_agentic: m.analysis_stage_agentic,
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

  // サブステップのライブ進捗（agentic ジョブが backbone 各段→学習生成→Twin Agent を進める様子, issue 069）。
  const progress = $derived(analysisRun.stages["agentic"]?.progress ?? null);
  const progressPct = $derived(progress && progress.total > 0 ? (progress.completed / progress.total) * 100 : 0);
  const stepTone: Record<string, string> = {
    pending: "text-muted-foreground",
    running: "text-debt-knowledge",
    completed: "text-success",
    failed: "text-destructive",
  };
  function stepMark(status: string): string {
    return status === "completed" ? "✓" : status === "failed" ? "×" : status === "running" ? "●" : "○";
  }
  // ブロックのバッジ状態を、属する子サブステップの進捗から導出（どのブロックがどこまで進んだかを示す）。
  // 子が無い（progress 未取得）ときは従来のステージ集約状態にフォールバック。
  function blockStatus(children: JobProgressStep[], fallback: StageStatus): StageStatus {
    if (children.length === 0) return fallback;
    if (children.some((s) => s.status === "failed")) return "FAILED";
    if (children.every((s) => s.status === "completed")) return "COMPLETED";
    if (children.some((s) => s.status === "running" || s.status === "completed")) return "PROCESSING";
    return fallback;
  }

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
  <!-- モーダルは常に同じ 3 行を表示し、変化するのは各行のステータス（未実行 → 処理中 → 完了）のみ（issue 069）。 -->
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
          {analysisRun.running
            ? m.analysis_run_running()
            : analysisRun.started
              ? m.analysis_regenerate()
              : m.analysis_run_cta()}
        </Button>
      </div>
    </div>
    {#if progress && progress.steps.length > 0}
      <!-- 全体進捗（確定プログレスバー）。各ブロックの子サブステップは下にネスト表示（issue 069）。 -->
      <div class="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
        <span>{m.analysis_progress_detail()}</span>
        <span class="tabular-nums">{Math.round(progressPct)}%</span>
      </div>
      <div class="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          class="h-full rounded-full bg-debt-knowledge/60 transition-all duration-500"
          style={`width:${progressPct}%`}
        ></div>
      </div>
    {/if}
    <ul class="flex flex-col gap-1.5">
      {#each STAGE_GROUPS as group (group.id)}
        {@const gv = groupView(group)}
        {@const children = progress ? progress.steps.filter((s) => s.group === group.id) : []}
        {@const bs = blockStatus(children, gv.status)}
        <li class="rounded-md border bg-background/40 px-3 py-2 text-sm">
          <div class="flex items-center gap-3">
            <span class={`w-16 shrink-0 text-xs font-medium ${statusTone[bs]}`}>{statusLabel(bs)}</span>
            <span class="min-w-0 flex-1 truncate">{groupLabel[group.labelKey]()}</span>
            {#if gv.status === "COMPLETED" && group.deepLink}
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
          </div>
          {#if children.length > 0}
            <!-- このブロックに属する内部サブステップ（どこまで・どの程度進んだか）。 -->
            <ul class="mt-2 flex flex-col gap-1 border-t pt-2 pl-0.5">
              {#each children as s (s.key)}
                <li class="flex items-center gap-2 text-xs">
                  <span class={`w-3 shrink-0 text-center ${stepTone[s.status] ?? "text-muted-foreground"}`}>
                    {stepMark(s.status)}
                  </span>
                  <span class={`min-w-0 flex-1 truncate ${s.status === "pending" ? "text-muted-foreground" : ""}`}>
                    {s.label}
                  </span>
                  {#if s.total != null && s.total > 0}
                    <span class="shrink-0 text-muted-foreground tabular-nums">{s.done ?? 0}/{s.total}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </li>
      {/each}
    </ul>
    {#if auth.isDemo}
      <p class="mt-2 text-xs leading-snug text-muted-foreground">{demoBlockMain}<br />{demoBlockHint}</p>
    {/if}
  </div>
</section>
