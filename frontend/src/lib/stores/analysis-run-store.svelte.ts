import { cancelAnalysis, getAnalysisStatus, getJob, recordTrendSnapshot, runAgenticAnalysis } from "$lib/api/client";

// 解析ラン・コックピットの共有状態（issue 037）。018 の stack-analysis-store のポーリング/状態遷移を
// 「ステージ集合 + 依存順 + deep-link」へ一般化したもの。コックピットと各サブページが同一 store を参照する。
export type StageStatus = "idle" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
export type StageId = "agentic";
export type RunContext = { orgSlug: string; projectSlug: string; owner: string; repo: string };

// job_id を返さないステージ（baseline-plans / baseline-quizzes は N 件ファンアウト）は enqueue 完了で COMPLETED 扱い。
type EnqueueResult = { job_id?: string; link?: string };
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

// 解析ステージは単一の agentic（ADK）解析に集約（issue 069 Increment 2）。「リポジトリ解析」= この 1 ジョブが
// サーバ側で検知/算出（feature/コード負債/KC/知識負債）＋ 学習プラン・ベースラインクイズの生成 ＋ 自律判断まで
// 行う。ブラウザは enqueue + ポーリングのみで、タブを閉じても後続生成が止まらない（ブラウザ依存の排除）。
export const STAGES: StageDef[] = [
  {
    id: "agentic",
    labelKey: "analysis_stage_agentic",
    jobType: "agentic_analysis",
    enqueue: (c) => runAgenticAnalysis(c.orgSlug, c.projectSlug),
    dependsOn: [],
    deepLink: (c) => _path(c, "/matrix"),
  },
];

// コックピット表示用グループ。ユーザーには従来どおり「技術負債の検知 / 理解負債の整理 / クイズと学習の生成」の
// 3 段階で見せる。技術負債・理解負債の検知は内部的には単一の agentic（ADK）解析が両方を生成するため、両グループとも
// `agentic` ステージを参照し同時に進む（表示上の段階分けはユーザーの分かりやすさのため）。
export type StageGroupDef = {
  id: string;
  labelKey: string;
  stageIds: StageId[];
  deepLink: ((ctx: RunContext) => string) | null;
};
export const STAGE_GROUPS: StageGroupDef[] = [
  {
    id: "g_technical",
    labelKey: "analysis_group_technical",
    stageIds: ["agentic"],
    deepLink: (c) => _path(c, "/matrix"),
  },
  {
    id: "g_knowledge",
    labelKey: "analysis_group_knowledge",
    stageIds: ["agentic"],
    deepLink: (c) => _path(c, "/galaxy"),
  },
  {
    id: "g_repay",
    labelKey: "analysis_group_repay",
    stageIds: ["agentic"],
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
    // 解析開始時に全フェーズを idle へリセットする。前回ランの COMPLETED 表示を引きずると、再解析で
    // 1 つ目だけ「処理中」で 2・3 つ目が「完了」のまま見え分かりづらいため、毎回クリーンな状態から始める。
    this.#generation += 1; // 直前ランの残ポーリングを中断
    this.stages = _initial();
    try {
      for (const def of STAGES) {
        const depsOk = def.dependsOn.every((d) => this.stages[d]?.status === "COMPLETED");
        if (depsOk) await this.runStage(def.id, ctx);
      }
      // 解析完了時点のコード品質・理解度を週次の推移点として記録（失敗してもランは壊さない、issue 067）。
      try {
        await recordTrendSnapshot(ctx.orgSlug, ctx.projectSlug);
      } catch {
        /* 記録失敗は無視（推移は次回の解析で更新される） */
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
    if (!res.job_id) {
      // ファンアウト系（学習プラン/確認クイズの一括生成）は単一 job を持たないため enqueue 完了で COMPLETED。
      this.#set(id, { status: "COMPLETED", link: res.link ?? def.deepLink?.(ctx) ?? null });
      return;
    }
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

  /** Cancel the current run from the UI: tell the server to CANCEL in-progress jobs, abort local
   * polls, and return to an idle state. Unblocks a cockpit stuck on a never-dispatched QUEUED job.
   * Resilient: the local state is cleared even if the server call fails. */
  async cancelRun(ctx: RunContext) {
    this.#generation += 1; // abort in-flight polls
    this.#runAllActive = false;
    try {
      await cancelAnalysis(ctx.orgSlug, ctx.projectSlug);
    } catch {
      /* clear locally regardless so the UI never stays locked */
    }
    this.stages = _initial(); // → started/running become false (derived from stages)
    this.#hydrated = true; // don't immediately re-pull the now-cancelled statuses
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
