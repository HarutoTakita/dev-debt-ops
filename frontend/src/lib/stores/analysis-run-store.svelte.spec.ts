import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobStatusResponse } from "$lib/api/schemas";

// API クライアントをモック（vi.hoisted で factory より前に確実に生成）。
const mocks = vi.hoisted(() => ({
  detectDebts: vi.fn(),
  detectKnowledgeDebts: vi.fn(),
  analyzeGalaxy: vi.fn(),
  generatePlan: vi.fn(),
  runAgentLoop: vi.fn(),
  getJob: vi.fn(),
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
  mocks.generatePlan.mockResolvedValue({ job_id: "j-p", plan_id: "plan-1" });
  mocks.runAgentLoop.mockResolvedValue({ job_id: "j-a", status: "QUEUED" });
  mocks.getJob.mockResolvedValue(job("COMPLETED", { agent_trace: ["done"] }));
});

describe("AnalysisRunStore", () => {
  it("runStage enqueues, polls to COMPLETED, and sets the deep-link", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("detect_code", CTX);
    expect(mocks.detectDebts).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.stages.detect_code.status).toBe("COMPLETED");
    expect(store.stages.detect_code.link).toBe("/acme/rosetta/matrix");
    expect(store.stages.detect_code.step).toBe("done");
  });

  it("plan_learning link carries the returned plan_id", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("plan_learning", CTX);
    expect(store.stages.plan_learning.link).toBe("/acme/rosetta/learning?planId=plan-1");
  });

  it("runAll runs every stage in dependency order (loop after detect)", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runAll(CTX);
    for (const id of ["detect_code", "detect_knowledge", "analyze_galaxy", "plan_learning", "loop_agents"]) {
      expect(store.stages[id].status).toBe("COMPLETED");
    }
    expect(mocks.runAgentLoop).toHaveBeenCalled();
  });

  it("a failed dependency skips its dependents but others still run", async () => {
    mocks.getJob.mockImplementation(async (id: string) =>
      id === "j-dc" ? job("FAILED", { error: "boom" }) : job("COMPLETED"),
    );
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runAll(CTX);
    expect(store.stages.detect_code.status).toBe("FAILED");
    expect(store.stages.loop_agents.status).toBe("idle"); // dependency failed → skipped
    expect(store.stages.analyze_galaxy.status).toBe("COMPLETED"); // independent → ran
  });

  it("a stage already running is not re-enqueued (dedup)", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    store.stages = { ...store.stages, detect_code: { status: "PROCESSING", jobId: "x", step: "", link: null } };
    await store.runStage("detect_code", CTX);
    expect(mocks.detectDebts).not.toHaveBeenCalled();
  });

  it("transitions to FAILED when enqueue throws", async () => {
    mocks.analyzeGalaxy.mockRejectedValue(new Error("nope"));
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("analyze_galaxy", CTX);
    expect(store.stages.analyze_galaxy.status).toBe("FAILED");
    expect(store.stages.analyze_galaxy.step).toBe("nope");
  });

  it("reset clears all stages to idle", async () => {
    const store = new AnalysisRunStore();
    store.pollIntervalMs = 1;
    await store.runStage("detect_code", CTX);
    store.reset();
    expect(store.stages.detect_code.status).toBe("idle");
    expect(store.started).toBe(false);
  });
});
