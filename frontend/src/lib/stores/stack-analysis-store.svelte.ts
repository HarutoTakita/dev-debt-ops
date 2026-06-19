import { analyzeStack, getJob, getStack } from "$lib/api/client";
import type { TechStack } from "$lib/api/schemas";
import { traceToStep, type StackStep } from "$lib/components/repo/stack-trace-steps";

// テックスタック解析の enqueue + ポーリングを司る Svelte 5 クラスベース runes ストア（issue 018）。
// `state` は UI 内部状態（job.status とは別物）。完了時は永続化済み TechStack に合流する。
class StackAnalysisStore {
  state = $state<"idle" | "queued" | "processing" | "done" | "error">("idle");
  trace = $state<string[]>([]);
  stack = $state<TechStack | null>(null);
  errorMsg = $state("");
  jobId: string | null = null;

  // ポーリング間隔（テストで上書き可能）。
  pollIntervalMs = 1500;
  #timer: ReturnType<typeof setTimeout> | null = null;

  // 進捗 UI 用: 最新 trace 行から人間可読なステップキーを導出（ラベルは呼び出し側で i18n）。
  currentStep = $derived<StackStep>(traceToStep(this.trace));

  async analyze(owner: string, repo: string) {
    this.reset();
    this.state = "queued";
    try {
      const job = await analyzeStack(owner, repo); // 202 {job_id}
      this.jobId = job.job_id;
      await this.poll(owner, repo);
    } catch (err) {
      this.#fail(err);
    }
  }

  async poll(owner: string, repo: string) {
    if (!this.jobId) return;
    try {
      const job = await getJob(this.jobId);
      this.trace = job.agent_trace ?? [];
      if (job.status === "COMPLETED") {
        // 完了時の TechStack はジョブに同梱されるが、無ければ GET .../stack で読む（不変 IF）。
        this.stack = job.tech_stack ?? (await getStack(owner, repo));
        this.state = "done";
        return;
      }
      if (job.status === "FAILED" || job.status === "CANCELLED") {
        this.state = "error";
        this.errorMsg = job.error ?? "";
        return;
      }
      this.state = "processing";
      this.#timer = setTimeout(() => void this.poll(owner, repo), this.pollIntervalMs);
    } catch (err) {
      this.#fail(err);
    }
  }

  cancel() {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = null;
  }

  reset() {
    this.cancel();
    this.state = "idle";
    this.trace = [];
    this.stack = null;
    this.errorMsg = "";
    this.jobId = null;
  }

  #fail(err: unknown) {
    this.cancel();
    this.state = "error";
    this.errorMsg = err instanceof Error ? err.message : "エラーが発生しました";
  }
}

export const stackAnalysis = new StackAnalysisStore();
export { StackAnalysisStore };
