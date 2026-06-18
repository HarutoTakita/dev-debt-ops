<script lang="ts">
  import Hourglass from "@lucide/svelte/icons/hourglass";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { ComingSoonError, assignDebt, createRepaymentPr, dismissDebt } from "$lib/api/client";
  import * as m from "$lib/paraglide/messages";

  // 返済 PR 作成 / 無視 / 担当割当 は Coming Soon プレースホルダ。場所と導線だけ用意し、
  // 押下で ComingSoonError を捕捉して「準備中」トーストを出す（本体は未実装）。
  type Props = { orgSlug: string; debtId: string };
  const { orgSlug, debtId }: Props = $props();

  async function run(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      if (e instanceof ComingSoonError) toast.info(m.debt_coming_soon_toast());
      else toast.error(e instanceof Error ? e.message : m.common_error_generic());
    }
  }
</script>

<div class="flex flex-wrap gap-2">
  <Button
    variant="outline"
    size="sm"
    class="gap-1.5 text-muted-foreground"
    onclick={() => run(() => createRepaymentPr(orgSlug, debtId))}
  >
    <Hourglass class="size-3.5" />
    {m.debt_action_create_pr()}
    <span class="text-xs opacity-70">{m.debt_action_soon_suffix()}</span>
  </Button>
  <Button
    variant="outline"
    size="sm"
    class="gap-1.5 text-muted-foreground"
    onclick={() => run(() => dismissDebt(orgSlug, debtId))}
  >
    <Hourglass class="size-3.5" />
    {m.debt_action_dismiss()}
    <span class="text-xs opacity-70">{m.debt_action_soon_suffix()}</span>
  </Button>
  <Button
    variant="outline"
    size="sm"
    class="gap-1.5 text-muted-foreground"
    onclick={() => run(() => assignDebt(orgSlug, debtId, ""))}
  >
    <Hourglass class="size-3.5" />
    {m.debt_action_assign()}
    <span class="text-xs opacity-70">{m.debt_action_soon_suffix()}</span>
  </Button>
</div>
