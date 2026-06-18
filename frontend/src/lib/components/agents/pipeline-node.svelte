<script lang="ts">
  import type { PipelineNode } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { agents } from "$lib/stores/agent-store.svelte";
  import AgentStatusIcon from "./agent-status-icon.svelte";
  import * as m from "$lib/paraglide/messages";

  // job_item.vue 写像。ステータス + 失敗時リトライ。
  let { node, pipelineId }: { node: PipelineNode; pipelineId: string } = $props();
</script>

<div class="flex items-center gap-2 rounded-md border bg-card px-2 py-1.5">
  <AgentStatusIcon status={node.status} />
  <span class="min-w-0 flex-1 truncate text-xs">{node.label}</span>
  {#if node.retryable}
    <Button variant="ghost" size="sm" class="h-6 px-2 text-xs" onclick={() => agents.retry(pipelineId, node.id)}>
      {m.agents_retry()}
    </Button>
  {/if}
</div>
