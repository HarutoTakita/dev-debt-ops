<script lang="ts">
  import { toast } from "svelte-sonner";
  import type { CodeDebt } from "$lib/api/schemas";
  import { createRepaymentPr, dismissDebt } from "$lib/api/client";
  import { Button } from "$lib/components/ui/button";
  import DebtStatusBadge from "$lib/components/matrix/debt-status-badge.svelte";
  import { categoryLabel, severityLabel } from "$lib/components/matrix/labels";
  import * as m from "$lib/paraglide/messages";

  // 選択中ファイルの技術負債を一覧し、返済PR（リファクタ）作成・無視を行う。返済ループを「コード改善」へ統合。
  type Props = { orgSlug: string; projectSlug: string; debts: CodeDebt[]; onchanged: () => void };
  const { orgSlug, projectSlug, debts, onchanged }: Props = $props();

  let busy = $state<string | null>(null);

  async function act(id: string, fn: () => Promise<unknown>, successMsg: string) {
    busy = id;
    try {
      await fn();
      toast.success(successMsg);
      onchanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = null;
    }
  }
</script>

<div class="flex flex-col gap-2 p-3">
  <h3 class="font-display text-sm font-semibold">{m.code_improve_file_heading()}</h3>
  {#if debts.length === 0}
    <p class="text-xs text-muted-foreground">{m.code_improve_file_empty()}</p>
  {:else}
    <ul class="flex flex-col gap-2">
      {#each debts as d (d.id)}
        <li class="rounded-lg border bg-card p-3">
          <div class="flex items-center gap-2 text-sm">
            <span class="font-medium">{categoryLabel(d)}</span>
            <span class="text-muted-foreground">· {severityLabel(d.severity)}</span>
            <span class="ml-auto"><DebtStatusBadge status={d.status} /></span>
          </div>
          {#if d.archaeology_notes}
            <p class="mt-1 line-clamp-2 text-xs text-muted-foreground">{d.archaeology_notes}</p>
          {/if}
          <div class="mt-2 flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy === d.id || d.status !== "open"}
              onclick={() =>
                act(d.id, () => createRepaymentPr(orgSlug, projectSlug, d.id), m.debt_repayment_pr_started())}
            >
              {m.debt_action_create_pr()}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy === d.id || d.status === "dismissed"}
              onclick={() => act(d.id, () => dismissDebt(orgSlug, projectSlug, d.id), m.project_settings_saved())}
            >
              {m.debt_action_dismiss()}
            </Button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>
