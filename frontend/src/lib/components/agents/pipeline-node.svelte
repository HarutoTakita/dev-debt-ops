<script lang="ts">
  import { toast } from "svelte-sonner";
  import type { PipelineNode } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { agents } from "$lib/stores/agent-store.svelte";
  import AgentStatusIcon from "./agent-status-icon.svelte";
  import * as m from "$lib/paraglide/messages";

  // job_item.vue 写像。ステータス + 失敗時リトライ。
  let { node, pipelineId }: { node: PipelineNode; pipelineId: string } = $props();

  // リトライ: status を analyzing にして「リトライ中…」を出し、少し後に結果へインライン遷移（モック）。
  function onRetry() {
    agents.retry(pipelineId, node.id);
    toast.info(m.agents_retry_running());
    setTimeout(() => agents.tick(pipelineId), 1200);
  }
</script>

<div class="flex items-center gap-2 rounded-md border bg-card px-2 py-1.5">
  <AgentStatusIcon status={node.status} />
  <span class="min-w-0 flex-1 truncate text-xs">{node.label}</span>
  {#if node.retryable}
    <Button variant="ghost" size="sm" class="h-6 px-2 text-xs" onclick={onRetry}>
      {m.agents_retry()}
    </Button>
  {/if}
</div>
