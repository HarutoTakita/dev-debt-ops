<script lang="ts">
  import type { NarrativeEvidence } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 考古学的根拠（§4.2）。初出コミット / AI 生成痕跡 / ADR 参照 / PR レビュー。
  let { evidence }: { evidence: NarrativeEvidence } = $props();

  const typeLabel: Record<NarrativeEvidence["type"], string> = {
    first_commit: m.agents_evidence_first_commit(),
    ai_generated: m.agents_evidence_ai_generated(),
    adr_reference: m.agents_evidence_adr(),
    pr_review: m.agents_evidence_pr_review(),
  };
</script>

<div class="rounded-md border bg-muted/30 px-2 py-1 text-xs">
  <div class="flex items-center gap-1.5">
    <span class="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">{typeLabel[evidence.type]}</span>
    <span class="font-medium">{evidence.label}</span>
  </div>
  {#if evidence.detail}<p class="mt-0.5 text-muted-foreground">{evidence.detail}</p>{/if}
</div>
