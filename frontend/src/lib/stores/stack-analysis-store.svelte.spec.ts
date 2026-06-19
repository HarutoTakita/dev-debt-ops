import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeStackJob, JobStatusResponse, TechStack } from "$lib/api/schemas";

// API クライアントをモック（vi.hoisted で factory より前に確実に生成）。
const mocks = vi.hoisted(() => ({
  analyzeStack: vi.fn(),
  getJob: vi.fn(),
  getStack: vi.fn(),
}));
vi.mock("$lib/api/client", () => mocks);

import { StackAnalysisStore } from "./stack-analysis-store.svelte";

const JOB: AnalyzeStackJob = { job_id: "11111111-1111-1111-1111-111111111111", status: "QUEUED" };

function techStack(): TechStack {
  const empty = {
    frameworks: [],
    databases: [],
    auth: [],
    container: [],
    infra: [],
    cicd: [],
    monitoring: [],
    testing: [],
    other: [],
  };
  return {
    owner: "acme",
    repo: "rosetta",
    analyzed_at: "2026-06-19T00:00:00+09:00",
    languages: [{ name: "Python", confidence: "high" }],
    categories: empty,
  };
}

function job(status: JobStatusResponse["status"], extra: Partial<JobStatusResponse> = {}): JobStatusResponse {
  return { id: JOB.job_id, status, agent_trace: [], ...extra };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("StackAnalysisStore", () => {
  it("analyze() enqueues, stores jobId, and reaches done on COMPLETED", async () => {
    mocks.analyzeStack.mockResolvedValue(JOB);
    mocks.getJob.mockResolvedValue(job("COMPLETED", { agent_trace: ["[done] save_stack"], tech_stack: techStack() }));
    const store = new StackAnalysisStore();

    await store.analyze("acme", "rosetta");

    expect(mocks.analyzeStack).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.jobId).toBe(JOB.job_id);
    expect(store.state).toBe("done");
    expect(store.stack?.languages[0].name).toBe("Python");
    // tech_stack がジョブに同梱されていれば getStack を別途呼ばない。
    expect(mocks.getStack).not.toHaveBeenCalled();
  });

  it("falls back to getStack when the completed job carries no tech_stack", async () => {
    mocks.analyzeStack.mockResolvedValue(JOB);
    mocks.getJob.mockResolvedValue(job("COMPLETED"));
    mocks.getStack.mockResolvedValue(techStack());
    const store = new StackAnalysisStore();

    await store.analyze("acme", "rosetta");

    expect(mocks.getStack).toHaveBeenCalledWith("acme", "rosetta");
    expect(store.state).toBe("done");
  });

  it("poll() exposes progress and currentStep while PROCESSING", async () => {
    const store = new StackAnalysisStore();
    store.jobId = JOB.job_id;
    mocks.getJob.mockResolvedValue(job("PROCESSING", { agent_trace: ["[call] read_file(path='x')"] }));

    await store.poll("acme", "rosetta");
    store.cancel(); // 次のポーリングがスケジュールされるので止める

    expect(store.state).toBe("processing");
    expect(store.trace).toEqual(["[call] read_file(path='x')"]);
    expect(store.currentStep).toBe("reading");
  });

  it("transitions to error on FAILED", async () => {
    mocks.analyzeStack.mockResolvedValue(JOB);
    mocks.getJob.mockResolvedValue(job("FAILED", { error: "boom" }));
    const store = new StackAnalysisStore();

    await store.analyze("acme", "rosetta");

    expect(store.state).toBe("error");
    expect(store.errorMsg).toBe("boom");
  });

  it("transitions to error when enqueue throws", async () => {
    mocks.analyzeStack.mockRejectedValue(new Error("nope"));
    const store = new StackAnalysisStore();

    await store.analyze("acme", "rosetta");

    expect(store.state).toBe("error");
    expect(store.errorMsg).toBe("nope");
  });
});
