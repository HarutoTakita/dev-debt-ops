import { getAgentProfiles, getPipeline, listActivities, retryAgentNode } from "$lib/api/client";
import type { AgentActivity, AgentKind, AgentPipeline, AgentProfile } from "$lib/api/schemas";

// Twin Agent 活動ストア（Svelte 5 クラスベース runes、issue 036）。
// profiles は静的配信、activities/pipelines は実 API。retry は実 PATCH、tick はパイプライン再取得。
class AgentStore {
  selectedKind = $state<AgentKind>("code_debt");
  profiles = $state<AgentProfile[]>([]);
  activities = $state<AgentActivity[]>([]);
  pipelines = $state<AgentPipeline[]>([]);
  #ctx: { orgSlug: string; projectSlug: string } | null = null;

  profile = $derived(this.profiles.find((p) => p.kind === this.selectedKind) ?? null);
  visibleActivities = $derived(this.activities.filter((a) => a.kind === this.selectedKind));
  visiblePipelines = $derived(this.pipelines.filter((p) => p.kind === this.selectedKind));

  // 実 API から人格・活動・各活動のパイプラインを取得する。
  async load(orgSlug: string, projectSlug: string) {
    this.#ctx = { orgSlug, projectSlug };
    this.profiles = await getAgentProfiles();
    this.activities = await listActivities(orgSlug, projectSlug);
    const ids = [...new Set(this.activities.map((a) => a.pipeline_id))];
    this.pipelines = await Promise.all(ids.map((id) => getPipeline(orgSlug, projectSlug, id)));
  }

  async #refreshPipeline(pipelineId: string) {
    if (!this.#ctx) return;
    const fresh = await getPipeline(this.#ctx.orgSlug, this.#ctx.projectSlug, pipelineId);
    this.pipelines = this.pipelines.map((p) => (p.id === pipelineId ? fresh : p));
  }

  // 失敗ノードの再実行（実 API）→ パイプライン再取得でライブ反映。
  async retry(pipelineId: string, nodeId: string) {
    if (!this.#ctx) return;
    try {
      await retryAgentNode(this.#ctx.orgSlug, this.#ctx.projectSlug, pipelineId, nodeId);
      await this.#refreshPipeline(pipelineId);
    } catch {
      /* keep previous state on failure */
    }
  }

  // ライブ更新: パイプラインを再取得する（擬似 tick の置き換え）。
  async tick(pipelineId: string) {
    await this.#refreshPipeline(pipelineId);
  }
}

export const agents = new AgentStore();
