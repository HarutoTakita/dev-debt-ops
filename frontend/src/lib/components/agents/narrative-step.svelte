<script lang="ts">
  import type { NarrativeStep } from "$lib/api/schemas";
  import * as Collapsible from "$lib/components/ui/collapsible";
  import AgentStatusIcon from "./agent-status-icon.svelte";
  import NarrativeEvidence from "./narrative-evidence.svelte";
  import * as m from "$lib/paraglide/messages";

  // 1 思考ステップ（MR ウィジェット写像）。一人称テキスト + ステータス + 折りたたみ根拠。
  let { step }: { step: NarrativeStep } = $props();
  let open = $state(false);
</script>

<div class="flex items-start gap-2 border-l-2 border-muted py-2 pl-3">
  <div class="mt-0.5"><AgentStatusIcon status={step.status} /></div>
  <div class="min-w-0 flex-1">
    <p class="text-sm">{step.message}</p>
    {#if step.evidence.length > 0}
      <Collapsible.Root bind:open>
        <Collapsible.Trigger class="mt-1 text-xs text-muted-foreground hover:text-foreground">
          {m.agents_evidence_toggle()}
          {open ? "▾" : "▸"}
        </Collapsible.Trigger>
        <Collapsible.Content class="mt-1 space-y-1">
          {#each step.evidence as e (e.label)}
            <NarrativeEvidence evidence={e} />
          {/each}
        </Collapsible.Content>
      </Collapsible.Root>
    {/if}
  </div>
</div>
