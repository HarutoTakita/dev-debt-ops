<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import type { DebtItem } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import { agents } from "$lib/stores/agent-store.svelte";
  import { formatKc, formatKcPct } from "$lib/format/kc";
  import DeveloperAvatar from "./developer-avatar.svelte";
  import DeveloperKey from "./developer-key.svelte";
  import { agentLabel, categoryLabel, kindLabel, severityLabel } from "./labels";

  // 要 Tooltip.Provider 祖先（呼び出し側ページで包む）。
  type Props = { debt: DebtItem };
  const { debt }: Props = $props();

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const agentHref = $derived(resolve(`/${orgSlug}/${projectSlug}/agents`));

  // detect → 推論への往復: agents 画面の kind を debt.kind に応じて事前選択する。
  function selectAgentKind() {
    agents.selectedKind = debt.kind === "code" ? "code_debt" : "knowledge_debt";
  }

  const rows = $derived([
    { label: m.debt_meta_severity(), value: severityLabel(debt.severity) },
    { label: m.debt_meta_kind(), value: `${kindLabel(debt.kind)} · ${categoryLabel(debt)}` },
    { label: m.debt_meta_adr(), value: debt.related_adr ?? m.debt_meta_none() },
    { label: m.debt_meta_cost(), value: m.list_estimated({ hours: debt.estimated_repay_hours }) },
    { label: m.debt_meta_kc(), value: formatKcPct(debt.knowledge_coverage) },
    { label: m.debt_meta_ai_prob(), value: `${Math.round(debt.ai_generation_prob * 100)}%` },
  ]);
</script>

<div class="divide-y rounded-lg border bg-card px-4">
  <div class="flex items-start justify-between gap-3 py-1.5 text-sm">
    <span class="shrink-0 text-muted-foreground">{m.debt_meta_agent()}</span>
    <a
      href={agentHref}
      onclick={selectAgentKind}
      title={m.matrix_view_agent_reasoning()}
      aria-label={m.matrix_view_agent_reasoning()}
      class="text-right underline-offset-2 hover:underline"
    >
      {agentLabel(debt.assigned_agent)}
    </a>
  </div>
  {#each rows as r (r.label)}
    <div class="flex items-start justify-between gap-3 py-1.5 text-sm">
      <span class="shrink-0 text-muted-foreground">{r.label}</span>
      <span class="text-right">{r.value}</span>
    </div>
  {/each}

  <div class="py-2">
    <div class="flex items-center justify-between gap-2">
      <span class="text-sm text-muted-foreground">{m.debt_meta_assigned()}</span>
      {#if debt.assigned_developers.length}<DeveloperKey />{/if}
    </div>
    {#if debt.assigned_developers.length}
      <ul class="mt-2 space-y-1.5">
        {#each debt.assigned_developers as dev (dev.github_handle)}
          <li class="flex items-center gap-2 text-xs">
            <DeveloperAvatar {dev} />
            <span class="font-mono">@{dev.github_handle}</span>
            <span class="ml-auto text-muted-foreground tabular-nums"
              >{formatKc(dev.coverage)} · {dev.certified_via}</span
            >
          </li>
        {/each}
      </ul>
    {:else}
      <p class="mt-1 text-xs text-muted-foreground">{m.debt_meta_none()}</p>
    {/if}
  </div>
</div>
