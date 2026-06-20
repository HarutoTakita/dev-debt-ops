import { analyzeGalaxy, detectDebts, detectKnowledgeDebts, generatePlan, getJob, runAgentLoop } from "$lib/api/client";

// 解析ラン・コックピットの共有状態（issue 037）。018 の stack-analysis-store のポーリング/状態遷移を
// 「ステージ集合 + 依存順 + deep-link」へ一般化したもの。コックピットと各サブページが同一 store を参照する。
export type StageStatus = "idle" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
export type RunContext = { orgSlug: string; projectSlug: string; owner: string; repo: string };

type EnqueueResult = { job_id: string; link?: string };
type StageDef = {
  id: string;
  labelKey: string;
  enqueue: (ctx: RunContext) => Promise<EnqueueResult>;
  dependsOn: string[];
  deepLink: ((ctx: RunContext) => string) | null;
};

const _path = (ctx: RunContext, suffix: string) => `/${ctx.orgSlug}/${ctx.projectSlug}${suffix}`;

// コアループのステージ集合（検知 → 分析 → 計画 → 返済〔=ループ束ね〕）。クイズ/返済 PR は
// ファイル/負債単位のため各 Map 詳細の責務（037 対象外）。
export const STAGES: StageDef[] = [
  {
    id: "detect_code",
    labelKey: "analysis_stage_detect_code",
    enqueue: (c) => detectDebts(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/matrix"),
  },
  {
    id: "detect_knowledge",
    labelKey: "analysis_stage_detect_knowledge",
    enqueue: (c) => detectKnowledgeDebts(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/matrix?kind=knowledge"),
  },
  {
    id: "analyze_galaxy",
    labelKey: "analysis_stage_analyze_galaxy",
    enqueue: (c) => analyzeGalaxy(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/galaxy"),
  },
  {
    id: "plan_learning",
    labelKey: "analysis_stage_plan_learning",
    enqueue: async (c) => {
      const { job_id, plan_id } = await generatePlan(c.orgSlug, c.projectSlug, {});
      return { job_id, link: _path(c, `/learning?planId=${plan_id}`) };
    },
    dependsOn: [],
    deepLink: (c) => _path(c, "/learning"),
  },
  {
    id: "loop_agents",
    labelKey: "analysis_stage_loop_agents",
    enqueue: (c) => runAgentLoop(c.orgSlug, c.projectSlug, "code_debt"),
    dependsOn: ["detect_code"],
    deepLink: (c) => _path(c, "/agents"),
  },
];

type StageState = { status: StageStatus; jobId: string | null; step: string; link: string | null };

function _initial(): Record<string, StageState> {
  return Object.fromEntries(STAGES.map((s) => [s.id, { status: "idle", jobId: null, step: "", link: null }]));
}

class AnalysisRunStore {
  stages = $state<Record<string, StageState>>(_initial());
  pollIntervalMs = 1500;
  #generation = 0; // bumped by cancel()/reset() to abort in-flight polls

  started = $derived(Object.values(this.stages).some((s) => s.status !== "idle"));
  running = $derived(Object.values(this.stages).some((s) => s.status === "QUEUED" || s.status === "PROCESSING"));

  #set(id: string, patch: Partial<StageState>) {
    this.stages = { ...this.stages, [id]: { ...this.stages[id], ...patch } };
  }

  /** Run all stages in dependency order; a failed dependency skips its dependents (others continue). */
  async runAll(ctx: RunContext) {
    for (const def of STAGES) {
      const depsOk = def.dependsOn.every((d) => this.stages[d]?.status === "COMPLETED");
      if (depsOk) await this.runStage(def.id, ctx);
    }
  }

  /** Enqueue one stage and poll to terminal. Idempotent: a QUEUED/PROCESSING stage is not re-run. */
  async runStage(id: string, ctx: RunContext) {
    const def = STAGES.find((s) => s.id === id);
    const cur = this.stages[id];
    if (!def || !cur || cur.status === "QUEUED" || cur.status === "PROCESSING") return;
    const gen = this.#generation;
    this.#set(id, { status: "QUEUED", step: "", link: null });
    let res: EnqueueResult;
    try {
      res = await def.enqueue(ctx);
    } catch (err) {
      this.#set(id, { status: "FAILED", step: err instanceof Error ? err.message : "" });
      return;
    }
    if (gen !== this.#generation) return; // cancelled mid-enqueue
    this.#set(id, { jobId: res.job_id, link: res.link ?? null });
    await this.#poll(id, ctx, def, gen);
  }

  async #poll(id: string, ctx: RunContext, def: StageDef, gen: number) {
    const jobId = this.stages[id].jobId;
    if (!jobId) return;
    while (gen === this.#generation) {
      let job;
      try {
        job = await getJob(jobId);
      } catch (err) {
        this.#set(id, { status: "FAILED", step: err instanceof Error ? err.message : "" });
        return;
      }
      if (gen !== this.#generation) return;
      const step = job.agent_trace?.at(-1) ?? "";
      if (job.status === "COMPLETED") {
        this.#set(id, { status: "COMPLETED", step, link: this.stages[id].link ?? def.deepLink?.(ctx) ?? null });
        return;
      }
      if (job.status === "FAILED" || job.status === "CANCELLED") {
        this.#set(id, { status: "FAILED", step: job.error ?? step });
        return;
      }
      this.#set(id, { status: "PROCESSING", step });
      await new Promise((r) => setTimeout(r, this.pollIntervalMs));
    }
  }

  cancel() {
    this.#generation += 1;
  }

  reset() {
    this.#generation += 1;
    this.stages = _initial();
  }
}

export const analysisRun = new AnalysisRunStore();
export { AnalysisRunStore };
