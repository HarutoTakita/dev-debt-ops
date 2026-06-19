import { beforeEach, describe, expect, it, vi } from "vitest";
import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import TechStackPanel from "./tech-stack-panel.svelte";
import type { TechStack } from "$lib/api/schemas";

const mocks = vi.hoisted(() => ({
  analyzeStack: vi.fn(),
  getJob: vi.fn(),
  getStack: vi.fn(),
}));
vi.mock("$lib/api/client", () => mocks);

const EMPTY_CATS = {
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

const STACK: TechStack = {
  owner: "acme",
  repo: "rosetta",
  analyzed_at: "2026-06-19T00:00:00+09:00",
  languages: [{ name: "Python", confidence: "high" }],
  categories: EMPTY_CATS,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TechStackPanel", () => {
  it("shows the analyze button when nothing is cached yet", async () => {
    mocks.getStack.mockResolvedValue(null);
    render(TechStackPanel, { owner: "acme", repo: "rosetta" });
    await expect.element(page.getByRole("button", { name: "解析する" })).toBeInTheDocument();
  });

  it("enqueues, shows progress, then renders the completed badges", async () => {
    mocks.getStack.mockResolvedValue(null);
    mocks.analyzeStack.mockResolvedValue({ job_id: "job-1", status: "QUEUED" });
    // First poll: still processing (progress UI), then completed with the persisted stack.
    mocks.getJob
      .mockResolvedValueOnce({ id: "job-1", status: "PROCESSING", agent_trace: ["[call] classify_stack({})"] })
      .mockResolvedValue({ id: "job-1", status: "COMPLETED", agent_trace: ["[done] save_stack"], tech_stack: STACK });

    render(TechStackPanel, { owner: "acme", repo: "rosetta" });
    await page.getByRole("button", { name: "解析する" }).click();

    // Progress step (classify_stack → "技術スタックを分類中…").
    await expect.element(page.getByText("技術スタックを分類中…")).toBeInTheDocument();
    // Completion合流: the language badge appears once polling (1.5s interval) reaches COMPLETED.
    await expect.element(page.getByText("Python"), { timeout: 5000 }).toBeInTheDocument();
  });

  it("renders cached badges on mount without analysing", async () => {
    mocks.getStack.mockResolvedValue(STACK);
    render(TechStackPanel, { owner: "acme", repo: "rosetta" });
    await expect.element(page.getByText("Python")).toBeInTheDocument();
    expect(mocks.analyzeStack).not.toHaveBeenCalled();
  });
});
