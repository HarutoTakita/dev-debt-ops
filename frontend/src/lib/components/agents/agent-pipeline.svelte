<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import type { AgentPipeline } from "$lib/api/schemas";
  import PipelineStageColumn from "./pipeline-stage-column.svelte";

  // パイプライングラフ写像。検知 → 分析 → 計画 → 返済 → 検証 を横に連結。
  let { pipeline }: { pipeline: AgentPipeline } = $props();
</script>

<div class="flex items-start gap-1 overflow-x-auto pb-2">
  {#each pipeline.stages as stage, i (stage.key)}
    {#if i > 0}
      <div class="mt-6 shrink-0 text-muted-foreground/40"><ChevronRight class="size-4" /></div>
    {/if}
    <PipelineStageColumn {stage} pipelineId={pipeline.id} />
  {/each}
</div>
