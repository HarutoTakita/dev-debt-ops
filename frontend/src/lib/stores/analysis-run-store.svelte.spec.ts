import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobStatusResponse } from "$lib/api/schemas";

// API クライアントをモック（vi.hoisted で factory より前に確実に生成）。
const mocks = vi.hoisted(() => ({
  detectDebts: vi.fn(),
  detectKnowledgeDebts: vi.fn(),
  analyzeGalaxy: vi.fn(),
  clusterFeatures: vi.fn(),
  generateBaselinePlans: vi.fn(),
  generateBaselineQuizzes: vi.fn(),
  recordTrendSnapshot: vi.fn(),
  getJob: vi.fn(),
  getAnalysisStatus: vi.fn(),
  cancelAnalysis: vi.fn(),
  runAgenticAnalysis: vi.fn(),
}));
vi.mock("$lib/api/client", () => mocks);

import { AnalysisRunStore } from "./analysis-run-store.svelte";

const CTX = { orgSlug: "acme", projectSlug: "rosetta", owner: "acme", repo: "rosetta" };

function job(status: JobStatusResponse["status"], extra: Partial<JobStatusResponse> = {}): JobStatusResponse {
  return { id: "j", status, agent_trace: [], ...extra };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.detectDebts.mockResolvedValue({ job_id: "j-dc", status: "QUEUED" });
  mocks.detectKnowledgeDebts.mockResolvedValue({ job_id: "j-dk", status: "QUEUED" });
  mocks.analyzeGalaxy.mockResolvedValue({ job_id: "j-g", status: "QUEUED" });
  mocks.clusterFeatures.mockResolvedValue({ job_id: "j-fc", status: "QUEUED" });
  mocks.generateBaselinePlans.mockResolvedValue({ created: 3 });
  mocks.generateBaselineQuizzes.mockResolvedValue({ created: 3 });
  mocks.getJob.mockResolvedValue(job("COMPLETED", { agent_trace: ["done"] }));
  mocks.runAgenticAnalysis.mockResolvedValue({ job_id: "j-tw", status: "QUEUED" });
});

describe("AnalysisRunStore", () => {
  it("agentic stage enqueues the Twin Agent run (issue 069) and polls to COMPLETED", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("agentic", CTX);
    expect(mocks.runAgenticAnalysis).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.stages.agentic.status).toBe("COMPLETED");
  });

  it("runAll runs the agentic stage to COMPLETED", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runAll(CTX);
    expect(store.stages.agentic.status).toBe("COMPLETED");
    expect(mocks.runAgenticAnalysis).toHaveBeenCalledTimes(1);
  });

  it("a stage already running is not re-enqueued (dedup)", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    store.stages = {
      ...store.stages,
      agentic: { status: "PROCESSING", jobId: "x", step: "", link: null, progress: null },
    };
    await store.runStage("agentic", CTX);
    expect(mocks.runAgenticAnalysis).not.toHaveBeenCalled();
  });

  it("transitions to FAILED when enqueue throws", async () => {
    mocks.runAgenticAnalysis.mockRejectedValue(new Error("nope"));
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("agentic", CTX);
    expect(store.stages.agentic.status).toBe("FAILED");
    expect(store.stages.agentic.step).toBe("nope");
  });

  it("reset clears all stages to idle", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("agentic", CTX);
    store.reset();
    expect(store.stages.agentic.status).toBe("idle");
    expect(store.started).toBe(false);
  });

  it("a second concurrent runAll is ignored (reentrancy guard)", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await Promise.all([store.runAll(CTX), store.runAll(CTX)]);
    // The second runAll returns immediately; the agentic stage is enqueued exactly once.
    expect(mocks.runAgenticAnalysis).toHaveBeenCalledTimes(1);
  });

  it("hydrate rebuilds the agentic stage from persisted jobs (survives reload)", async () => {
    mocks.getAnalysisStatus.mockResolvedValue({
      jobs: { agentic_analysis: { status: "COMPLETED", job_id: "j1" } },
    });
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.hydrate(CTX);
    expect(store.started).toBe(true);
    expect(store.stages.agentic.status).toBe("COMPLETED");
    expect(store.stages.agentic.link).toBe("/acme/rosetta/matrix");
    expect(mocks.runAgenticAnalysis).not.toHaveBeenCalled(); // hydration does not enqueue
  });

  it("hydrate restores the job's sub-step progress so child statuses persist after reload (issue 252)", async () => {
    mocks.getAnalysisStatus.mockResolvedValue({
      jobs: { agentic_analysis: { status: "COMPLETED", job_id: "j1" } },
    });
    const progress = {
      steps: [{ key: "code_debt_detection", label: "コード負債の検知", group: "g_technical", status: "completed" }],
      completed: 1,
      total: 1,
    };
    mocks.getJob.mockResolvedValue(job("COMPLETED", { progress }));
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.hydrate(CTX);
    expect(mocks.getJob).toHaveBeenCalledWith("j1");
    expect(store.stages.agentic.progress).toEqual(progress);
  });

  it("hydrate is a no-op once a run has started", async () => {
    mocks.getAnalysisStatus.mockResolvedValue({
      jobs: { agentic_analysis: { status: "COMPLETED", job_id: "j1" } },
    });
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("agentic", CTX); // a run has started
    await store.hydrate(CTX);
    expect(mocks.getAnalysisStatus).not.toHaveBeenCalled();
  });
});
