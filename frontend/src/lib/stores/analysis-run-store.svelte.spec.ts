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

  it("confirm_quizzes generates baseline quizzes and links to the quizzes hub", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("confirm_quizzes", CTX);
    expect(mocks.generateBaselineQuizzes).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.stages.confirm_quizzes.status).toBe("COMPLETED");
    expect(store.stages.confirm_quizzes.link).toBe("/acme/rosetta/quizzes");
  });

  it("plan_learning generates baseline plans and links to the learning hub", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("plan_learning", CTX);
    expect(mocks.generateBaselinePlans).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.stages.plan_learning.status).toBe("COMPLETED");
    expect(store.stages.plan_learning.link).toBe("/acme/rosetta/learning");
  });

  it("runAll runs every stage to COMPLETED", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runAll(CTX);
    for (const id of ["agentic", "plan_learning", "confirm_quizzes"]) {
      expect(store.stages[id].status).toBe("COMPLETED");
    }
  });

  it("a failed agentic stage skips its dependents", async () => {
    mocks.runAgenticAnalysis.mockResolvedValue({ job_id: "j-ag", status: "QUEUED" });
    mocks.getJob.mockImplementation(async (id: string) =>
      id === "j-ag" ? job("FAILED", { error: "boom" }) : job("COMPLETED"),
    );
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runAll(CTX);
    expect(store.stages.agentic.status).toBe("FAILED");
    expect(store.stages.plan_learning.status).toBe("idle"); // dependency failed → skipped
  });

  it("a stage already running is not re-enqueued (dedup)", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    store.stages = { ...store.stages, agentic: { status: "PROCESSING", jobId: "x", step: "", link: null } };
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

  it("hydrate rebuilds stage status from persisted jobs (survives reload)", async () => {
    mocks.getAnalysisStatus.mockResolvedValue({
      jobs: {
        agentic_analysis: { status: "COMPLETED", job_id: "j1" },
        learning_plan_generation: { status: "FAILED", job_id: "j2" },
      },
    });
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.hydrate(CTX);
    expect(store.started).toBe(true);
    expect(store.stages.agentic.status).toBe("COMPLETED");
    expect(store.stages.agentic.link).toBe("/acme/rosetta/matrix");
    expect(store.stages.plan_learning.status).toBe("FAILED");
    expect(store.stages.confirm_quizzes.status).toBe("idle"); // no job → stays idle
    expect(mocks.runAgenticAnalysis).not.toHaveBeenCalled(); // hydration does not enqueue
  });

  it("hydrate is a no-op once a run has started", async () => {
    mocks.getAnalysisStatus.mockResolvedValue({
      jobs: { agentic_analysis: { status: "COMPLETED", job_id: "j1" } },
    });
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("plan_learning", CTX); // a run has started
    await store.hydrate(CTX);
    expect(mocks.getAnalysisStatus).not.toHaveBeenCalled();
  });

  it("runAll resets stale stages so a skipped (failed-dependency) stage isn't shown as stale-completed", async () => {
    mocks.runAgenticAnalysis.mockResolvedValue({ job_id: "j-ag", status: "QUEUED" });
    mocks.getJob.mockImplementation(async (id: string) =>
      id === "j-ag" ? job("FAILED", { error: "boom" }) : job("COMPLETED"),
    );
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    // 前回ランの残り表示: plan_learning が COMPLETED のまま。
    store.stages = { ...store.stages, plan_learning: { status: "COMPLETED", jobId: "old", step: "", link: "/old" } };
    await store.runAll(CTX);
    // agentic が失敗 → 依存する plan_learning はスキップ。開始時リセットで idle へ戻り、前回表示を引きずらない。
    expect(store.stages.agentic.status).toBe("FAILED");
    expect(store.stages.plan_learning.status).toBe("idle");
  });
});
