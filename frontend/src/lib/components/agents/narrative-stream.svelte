<script lang="ts">
  import type { AgentActivity } from "$lib/api/schemas";
  import NarrativeStep from "./narrative-step.svelte";

  // 縦積みのナラティブ思考ストリーム（活動ごとに見出し + 思考ステップ列）。
  let { activities }: { activities: AgentActivity[] } = $props();
</script>

<div class="space-y-5">
  {#each activities as act (act.id)}
    <div>
      <h3 class="font-display text-sm font-semibold">{act.headline}</h3>
      <div class="mt-2">
        {#each act.steps as step (step.id)}
          <NarrativeStep {step} />
        {/each}
      </div>
    </div>
  {/each}
</div>
