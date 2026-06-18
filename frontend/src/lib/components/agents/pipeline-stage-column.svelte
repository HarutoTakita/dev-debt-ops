<script lang="ts">
  import type { PipelineStage } from "$lib/api/schemas";
  import PipelineNode from "./pipeline-node.svelte";

  // stage_column_component.vue 写像。ステージ名 + ノード縦積み。
  let { stage, pipelineId }: { stage: PipelineStage; pipelineId: string } = $props();
</script>

<div class="flex w-28 shrink-0 flex-col gap-2">
  <div class="text-center text-xs font-medium text-muted-foreground">{stage.label}</div>
  {#each stage.nodes as node (node.id)}
    <PipelineNode {node} {pipelineId} />
  {/each}
</div>
