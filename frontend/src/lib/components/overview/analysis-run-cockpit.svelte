<script lang="ts">
  import type { ResolvedPathname } from "$app/types";
  import { Button } from "$lib/components/ui/button";
  import {
    analysisRun,
    AGENTIC_SUBSTEPS,
    STAGES,
    STAGE_GROUPS,
    type RunContext,
    type StageGroupDef,
    type StageStatus,
  } from "$lib/stores/analysis-run-store.svelte";
  import { auth } from "$lib/stores/auth.svelte";
  import * as m from "$lib/paraglide/messages";

  // 解析は GitHub リポジトリの読み取りを伴うため、ゲストデモでは実行不可（issue 069）。
  const demoBlockMain = m.demo_block_main();
  const demoBlockHint = m.demo_block_hint();
  const demoBlockTitle = `${demoBlockMain}${demoBlockHint}`;
  // 解析クレジット（issue 298）: 有効時は残高 0 で実行不可。実行後は残高を再取得して表示を更新する。
  const creditsBlockTitle = m.credits_block_title();
  async function runAnalysis() {
    await analysisRun.runAll(ctx);
    await auth.refreshUser(); // 1 クレジット消費後の残高を反映
  }
  // フル再解析: 差分を無視して全体を再解析（機能をフル再クラスタ）。既存 run がある場合のみ意味を持つ。
  async function runFullAnalysis() {
    await analysisRun.runAll({ ...ctx, full: true });
    await auth.refreshUser();
  }

  // 解析ラン・コックピット。生成導線は単一の主 CTA に集約（issue 064/069）。モーダル上部の「リポジトリ解析」
  // タイトルと重複するため親ブロック見出しは置かず、4 ブロック（リポジトリ探索 / 技術負債の検知 / 理解負債の整理 /
  // クイズと学習の生成）を直接並べる。各ブロックは内部ステージの集約状態と実行中サブステップを示す。
  type Props = { ctx: RunContext };
  const { ctx }: Props = $props();

  const groupLabel: Record<string, () => string> = {
    analysis_group_explore: m.analysis_group_explore,
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
  // 内部サブステップのラベル（実行前から各ブロックの内訳を出すための静的カタログ用, issue 244）。
  const substepLabel: Record<string, () => string> = {
    analysis_substep_base_analysis: m.analysis_substep_base_analysis,
    analysis_substep_feature_clustering: m.analysis_substep_feature_clustering,
    analysis_substep_code_debt_detection: m.analysis_substep_code_debt_detection,
    analysis_substep_kc_analysis: m.analysis_substep_kc_analysis,
    analysis_substep_knowledge_debt_detection: m.analysis_substep_knowledge_debt_detection,
    analysis_substep_stack_analysis: m.analysis_substep_stack_analysis,
    analysis_substep_baseline: m.analysis_substep_baseline,
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

  // サブステップのライブ進捗（agentic ジョブが エージェント解析→backbone 各段→学習生成 を進める様子, issue 069/275）。
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
  // 実行中（PROCESSING / running）の水色ステータスは点滅（animate-pulse）させ「進行中」を視覚的に強調する。
  function tone(base: string, running: boolean): string {
    return running ? `${base} animate-pulse` : base;
  }
  // 表示用サブステップ。実行前から静的カタログ（AGENTIC_SUBSTEPS）で全件を pending 表示し、ライブ進捗が
  // 来たら key 一致で status/done/total を上書きする（issue 244）。これで「初めから詳細項目が並び、実行で
  // ステータスだけ変化する」挙動になる。
  type RenderStep = { key: string; label: string; status: string; done: number | null; total: number | null };
  function childrenFor(groupId: string): RenderStep[] {
    const live = new Map((progress?.steps ?? []).map((s) => [s.key, s]));
    // ライブ進捗が無い子の既定ステータス。解析が完了済みなら「完了」を維持する（再マウントや progress 欠落で
    // 子が pending に戻って“空”に見えるのを防ぐ, issue 252）。未実行/実行中は pending。
    const fallback = analysisRun.stages["agentic"]?.status === "COMPLETED" ? "completed" : "pending";
    return AGENTIC_SUBSTEPS.filter((d) => d.group === groupId).map((d) => {
      const s = live.get(d.key);
      return {
        key: d.key,
        label: substepLabel[d.labelKey](),
        status: s?.status ?? fallback,
        done: s?.done ?? null,
        total: s?.total ?? null,
      };
    });
  }
  // ブロックのバッジ状態を、属する子サブステップの進捗から導出（どのブロックがどこまで進んだかを示す）。
  // 全件 pending（実行前）のときは従来のステージ集約状態にフォールバック。
  function blockStatus(children: RenderStep[], fallback: StageStatus): StageStatus {
    if (children.some((s) => s.status === "failed")) return "FAILED";
    if (children.length > 0 && children.every((s) => s.status === "completed")) return "COMPLETED";
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
  <!-- モーダルは常に同じ親ブロック＋子サブステップを表示し、変化するのは各行のステータス（未実行 →
       処理中 → 完了）のみ（issue 069 / 244）。子は実行前から並び、実行でステータスだけが進む。 -->
  <div class="rounded-lg border bg-card p-4">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="font-display text-sm font-semibold">{m.analysis_run_title()}</h2>
      <div class="flex items-center gap-2">
        {#if analysisRun.running}
          <Button variant="outline" size="sm" class="h-7 px-2 text-xs" onclick={() => analysisRun.cancelRun(ctx)}>
            {m.common_cancel()}
          </Button>
        {/if}
        {#if analysisRun.started && !analysisRun.running}
          <!-- フル再解析: 既存 run がある時だけ。差分ではなく全体を再クラスタ（理解度は保持）。 -->
          <Button
            variant="ghost"
            size="sm"
            class="h-7 px-2 text-xs"
            disabled={auth.isDemo || auth.analysisBlocked}
            title={m.analysis_full_hint()}
            onclick={runFullAnalysis}
          >
            {m.analysis_full_reanalyze()}
          </Button>
        {/if}
        <Button
          variant="outline"
          size="sm"
          class="h-7 px-2 text-xs"
          disabled={analysisRun.running || auth.isDemo || auth.analysisBlocked}
          title={auth.isDemo ? demoBlockTitle : auth.analysisBlocked ? creditsBlockTitle : undefined}
          onclick={runAnalysis}
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
      <div class="mb-1.5 flex items-center justify-end text-xs text-muted-foreground">
        <span class="tabular-nums">{Math.round(progressPct)}%</span>
      </div>
      <div class="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          class="h-full rounded-full bg-debt-knowledge/60 transition-all duration-500"
          style={`width:${progressPct}%`}
        ></div>
      </div>
    {/if}
    <!-- 解析タスクの各ブロック（リポジトリ探索 / 技術負債の検知 / 理解負債の整理 / クイズと学習の生成）。
         「リポジトリ解析」タイトルと重複するため親ブロックの見出しは置かず、各ブロックを直接並べる。 -->
    <ul class="flex flex-col gap-1.5">
      {#each STAGE_GROUPS as group (group.id)}
        {@const gv = groupView(group)}
        {@const children = childrenFor(group.id)}
        {@const bs = blockStatus(children, gv.status)}
        <li class="rounded-md border bg-background/40 px-3 py-2 text-sm">
          <div class="flex items-center gap-3">
            <span class={`w-16 shrink-0 text-xs font-medium ${tone(statusTone[bs], bs === "PROCESSING")}`}
              >{statusLabel(bs)}</span
            >
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
                  <span
                    class={`w-3 shrink-0 text-center ${tone(stepTone[s.status] ?? "text-muted-foreground", s.status === "running")}`}
                  >
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
    {:else if auth.creditsEnabled}
      <p class="mt-2 text-xs leading-snug text-muted-foreground">
        {m.account_field_credits()}:
        <span class="font-medium tabular-nums text-foreground">{auth.analysisCredits}</span>
        {#if auth.analysisBlocked}<br />{m.credits_exhausted_hint()}{/if}
      </p>
    {/if}
  </div>
</section>
