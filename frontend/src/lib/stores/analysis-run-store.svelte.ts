import {
  analyzeGalaxy,
  clusterFeatures,
  detectDebts,
  detectKnowledgeDebts,
  generatePlan,
  getAnalysisStatus,
  getJob,
} from "$lib/api/client";

// 解析ラン・コックピットの共有状態（issue 037）。018 の stack-analysis-store のポーリング/状態遷移を
// 「ステージ集合 + 依存順 + deep-link」へ一般化したもの。コックピットと各サブページが同一 store を参照する。
export type StageStatus = "idle" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
export type StageId = "detect_code" | "detect_knowledge" | "analyze_galaxy" | "cluster_features" | "plan_learning";
export type RunContext = { orgSlug: string; projectSlug: string; owner: string; repo: string };

type EnqueueResult = { job_id: string; link?: string };
type StageDef = {
  id: string;
  labelKey: string;
  // 対応する JobType 値（analysis-status での状態復元キー）。
  jobType: string;
  enqueue: (ctx: RunContext) => Promise<EnqueueResult>;
  dependsOn: string[];
  deepLink: ((ctx: RunContext) => string) | null;
};

const _path = (ctx: RunContext, suffix: string) => `/${ctx.orgSlug}/${ctx.projectSlug}${suffix}`;

// コアループのステージ集合（検知 → 分析 → 計画）。クイズ/返済 PR は
// ファイル/負債単位のため各 Map 詳細の責務（037 対象外）。
export const STAGES: StageDef[] = [
  {
    id: "detect_code",
    labelKey: "analysis_stage_detect_code",
    jobType: "code_debt_detection",
    enqueue: (c) => detectDebts(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/matrix"),
  },
  {
    id: "detect_knowledge",
    labelKey: "analysis_stage_detect_knowledge",
    jobType: "knowledge_debt_detection",
    enqueue: (c) => detectKnowledgeDebts(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/matrix?kind=knowledge"),
  },
  {
    id: "analyze_galaxy",
    labelKey: "analysis_stage_analyze_galaxy",
    jobType: "kc_analysis",
    enqueue: (c) => analyzeGalaxy(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/galaxy"),
  },
  {
    // 機能（feature）クラスタリング。単元（学習）・機能粒度ビュー・機能クイズの前提（issue 052）。
    id: "cluster_features",
    labelKey: "analysis_stage_cluster_features",
    jobType: "feature_clustering",
    enqueue: (c) => clusterFeatures(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/learning"),
  },
  {
    id: "plan_learning",
    labelKey: "analysis_stage_plan_learning",
    jobType: "learning_plan_generation",
    enqueue: async (c) => {
      const { job_id, plan_id } = await generatePlan(c.orgSlug, c.projectSlug, {});
      return { job_id, link: _path(c, `/learning?planId=${plan_id}`) };
    },
    dependsOn: [],
    deepLink: (c) => _path(c, "/learning"),
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

  #runAllActive = false; // reentrancy guard: a second runAll (fast double-click / two pages) is ignored
  #hydrated = false; // guards one-shot rehydration per project (cleared on reset)

  /** Rehydrate stage status from persisted jobs so a page reload doesn't reset the cockpit.

   * Reads the latest job per stage (``GET .../analysis-status``) and reflects COMPLETED / FAILED,
   * resuming polling for any still-running stage. No-op once a run has started or after hydrating.
   */
  async hydrate(ctx: RunContext) {
    if (this.started || this.#hydrated) return;
    this.#hydrated = true;
    let data;
    try {
      data = await getAnalysisStatus(ctx.orgSlug, ctx.projectSlug);
    } catch {
      this.#hydrated = false; // allow a later retry
      return;
    }
    if (this.started) return; // a run started while we awaited the fetch
    const gen = this.#generation;
    for (const def of STAGES) {
      const entry = data.jobs[def.jobType];
      if (!entry) continue;
      if (entry.status === "COMPLETED") {
        this.#set(def.id, { status: "COMPLETED", jobId: entry.job_id, link: def.deepLink?.(ctx) ?? null });
      } else if (entry.status === "FAILED" || entry.status === "CANCELLED") {
        this.#set(def.id, { status: "FAILED", jobId: entry.job_id });
      } else {
        // QUEUED / PROCESSING — resume polling from where it left off.
        this.#set(def.id, { status: "PROCESSING", jobId: entry.job_id });
        void this.#poll(def.id, ctx, def, gen);
      }
    }
  }

  /** Run all stages in dependency order; a failed dependency skips its dependents (others continue). */
  async runAll(ctx: RunContext) {
    if (this.#runAllActive) return; // a run is already orchestrating; don't interleave a second loop
    this.#runAllActive = true;
    try {
      for (const def of STAGES) {
        const depsOk = def.dependsOn.every((d) => this.stages[d]?.status === "COMPLETED");
        if (depsOk) await this.runStage(def.id, ctx);
      }
    } finally {
      this.#runAllActive = false;
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
    this.#runAllActive = false;
    this.#hydrated = false;
    this.stages = _initial();
  }
}

export const analysisRun = new AnalysisRunStore();
export const ALL_STAGE_IDS: StageId[] = STAGES.map((s) => s.id as StageId);
export { AnalysisRunStore };
