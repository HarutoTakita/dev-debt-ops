<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
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

  // 逆リンク（rank 24）: evidence.href が "/matrix/<debtId>" 形のとき、現在の org/project に
  // スコープした Matrix 詳細へ戻れるようにする（resolve() は href 属性内で直接呼ぶ）。
  const target = $derived.by(() => {
    const match = evidence.href?.match(/^\/matrix\/(.+)$/);
    const { org, project } = page.params;
    if (!match || !org || !project) return null;
    return { org, project, debtId: match[1] };
  });
</script>

{#snippet body()}
  <div class="flex items-center gap-1.5">
    <span class="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">{typeLabel[evidence.type]}</span>
    <span class="font-medium">{evidence.label}</span>
  </div>
  {#if evidence.detail}<p class="mt-0.5 text-muted-foreground">{evidence.detail}</p>{/if}
{/snippet}

{#if target}
  <a
    href={resolve(`/${target.org}/${target.project}/matrix/${target.debtId}`)}
    class="block rounded-md border bg-muted/30 px-2 py-1 text-xs transition-colors hover:bg-muted/60"
    title={m.agents_evidence_view_debt()}
  >
    {@render body()}
  </a>
{:else}
  <div class="rounded-md border bg-muted/30 px-2 py-1 text-xs">
    {@render body()}
  </div>
{/if}
