<script lang="ts">
  import Hourglass from "@lucide/svelte/icons/hourglass";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { ComingSoonError, createRepaymentPr, dismissDebt } from "$lib/api/client";
  import * as m from "$lib/paraglide/messages";

  // 無視（dismiss, issue 031）と返済 PR 作成（issue 033）は実 API。担当割当は handle 選択 UI が
  // 未実装のため Coming Soon プレースホルダのまま。
  type Props = { orgSlug: string; projectSlug: string; debtId: string };
  const { orgSlug, projectSlug, debtId }: Props = $props();

  async function run(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      if (e instanceof ComingSoonError) toast.info(m.debt_coming_soon_toast());
      else toast.error(e instanceof Error ? e.message : m.common_error_generic());
    }
  }

  async function dismiss() {
    try {
      await dismissDebt(orgSlug, projectSlug, debtId);
      toast.success(m.project_settings_saved());
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    }
  }

  async function createPr() {
    try {
      await createRepaymentPr(orgSlug, projectSlug, debtId);
      toast.success(m.debt_repayment_pr_started());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    }
  }
</script>

<div class="flex flex-wrap gap-2">
  <Button variant="outline" size="sm" class="gap-1.5" onclick={createPr}>
    {m.debt_action_create_pr()}
  </Button>
  <Button variant="outline" size="sm" class="gap-1.5" onclick={dismiss}>
    {m.debt_action_dismiss()}
  </Button>
  <Button
    variant="outline"
    size="sm"
    class="gap-1.5 text-muted-foreground"
    onclick={() => run(() => Promise.reject(new ComingSoonError()))}
  >
    <Hourglass class="size-3.5" />
    {m.debt_action_assign()}
    <span class="text-xs opacity-70">{m.debt_action_soon_suffix()}</span>
  </Button>
</div>
