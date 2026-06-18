import type { AgentActivity, AgentKind, AgentPipeline, AgentProfile } from "$lib/api/schemas";
import { MOCK_ACTIVITIES, MOCK_PIPELINES, MOCK_PROFILES } from "$lib/mocks/agent-activity";

// Twin Agent 活動ストア（Svelte 5 クラスベース runes）。
// 実エージェント連携は後続 issue。当面はモック + ライブ更新シミュレーション。
class AgentStore {
  selectedKind = $state<AgentKind>("code_debt");
  profiles = $state<AgentProfile[]>([]);
  activities = $state<AgentActivity[]>([]);
  pipelines = $state<AgentPipeline[]>([]);

  profile = $derived(this.profiles.find((p) => p.kind === this.selectedKind) ?? null);
  visibleActivities = $derived(this.activities.filter((a) => a.kind === this.selectedKind));
  visiblePipelines = $derived(this.pipelines.filter((p) => p.kind === this.selectedKind));

  loadMock() {
    if (this.profiles.length) return; // 冪等
    this.profiles = MOCK_PROFILES;
    this.activities = MOCK_ACTIVITIES;
    this.pipelines = MOCK_PIPELINES;
  }

  #findNode(pipelineId: string, nodeId: string) {
    return this.pipelines
      .find((p) => p.id === pipelineId)
      ?.stages.flatMap((s) => s.nodes)
      .find((n) => n.id === nodeId);
  }

  // 失敗ノードのリトライ（モック上のライブ更新シミュレーション）
  retry(pipelineId: string, nodeId: string) {
    const node = this.#findNode(pipelineId, nodeId);
    if (node) {
      node.status = "analyzing";
      node.retryable = false;
    }
  }

  // 進行中ノードを次状態へ進める擬似ライブ更新（デモ用）。
  tick(pipelineId: string) {
    const pipeline = this.pipelines.find((p) => p.id === pipelineId);
    if (!pipeline) return;
    const nodes = pipeline.stages.flatMap((s) => s.nodes);
    const running = nodes.find(
      (n) =>
        n.status === "scanning" ||
        n.status === "analyzing" ||
        n.status === "creating_pr" ||
        n.status === "running_quiz",
    );
    if (running) {
      running.status = "succeeded";
      return;
    }
    const pending = nodes.find((n) => n.status === "pending");
    if (pending) pending.status = "analyzing";
  }
}

export const agents = new AgentStore();
