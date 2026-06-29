<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import UserPlus from "@lucide/svelte/icons/user-plus";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { createDebtIssue, createRepaymentPr } from "$lib/api/client";
  import type { DebtItem } from "$lib/api/schemas";
  import { members } from "$lib/stores/members-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード負債への 2 つの対応経路（issue 210）:
  //   AI に頼む  = 返済 PR を自動生成（Gemini が修正案、issue 033）
  //   人に頼む    = GitHub Issue を作成（任意でワークスペースのユーザーを担当に指定）
  type Props = { orgSlug: string; projectSlug: string; debt: DebtItem };
  const { orgSlug, projectSlug, debt }: Props = $props();

  // related_pr / related_issue は code 負債のみ。knowledge 負債では undefined。
  const relatedPr = $derived(debt.kind === "code" ? debt.related_pr : null);
  const relatedIssue = $derived(debt.kind === "code" ? debt.related_issue : null);

  let busy = $state(false);

  // 担当候補（ワークスペースのメンバー）を読み込む。
  $effect(() => {
    if (orgSlug) void members.load(orgSlug);
  });
  const memberList = $derived(members.members);

  async function createPr() {
    busy = true;
    try {
      await createRepaymentPr(orgSlug, projectSlug, debt.id);
      toast.success(m.debt_repayment_pr_started());
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }

  // assigneeUserId 未指定なら担当者なしで作成。
  async function createIssue(assigneeUserId?: string) {
    busy = true;
    try {
      await createDebtIssue(orgSlug, projectSlug, debt.id, assigneeUserId);
      toast.success(m.debt_issue_created());
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }
</script>

<div class="grid gap-3 sm:grid-cols-2">
  <!-- AI に頼む: 返済 PR を自動生成 -->
  <section class="flex flex-col gap-2 rounded-lg border bg-card p-3">
    <div class="flex items-center gap-1.5 text-sm font-medium">
      <Bot class="size-4 text-debt-knowledge" />
      {m.debt_path_ai_title()}
    </div>
    <p class="text-xs text-muted-foreground">{m.debt_path_ai_desc()}</p>
    {#if relatedPr}
      <!-- 外部 URL（GitHub PR）。SPA ルートではないため resolve() は適用しない -->
      <!-- eslint-disable svelte/no-navigation-without-resolve -->
      <a
        href={relatedPr}
        target="_blank"
        rel="noopener noreferrer"
        class="mt-auto inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        <ExternalLink class="size-3.5" />
        {m.debt_view_pr()}
      </a>
      <!-- eslint-enable svelte/no-navigation-without-resolve -->
    {:else}
      <Button class="mt-auto w-fit" variant="outline" size="sm" disabled={busy} onclick={createPr}>
        {m.debt_action_create_pr()}
      </Button>
    {/if}
  </section>

  <!-- 人に頼む: 担当割り当て + GitHub Issue -->
  <section class="flex flex-col gap-2 rounded-lg border bg-card p-3">
    <div class="flex items-center gap-1.5 text-sm font-medium">
      <UserPlus class="size-4 text-debt-code" />
      {m.debt_path_human_title()}
    </div>
    <p class="text-xs text-muted-foreground">{m.debt_path_human_desc()}</p>
    {#if relatedIssue}
      <!-- 外部 URL（GitHub Issue）。SPA ルートではないため resolve() は適用しない -->
      <!-- eslint-disable svelte/no-navigation-without-resolve -->
      <a
        href={relatedIssue}
        target="_blank"
        rel="noopener noreferrer"
        class="mt-auto inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        <ExternalLink class="size-3.5" />
        {m.debt_view_issue()}
      </a>
      <!-- eslint-enable svelte/no-navigation-without-resolve -->
    {:else}
      <!-- Issue を作成ボタン。押すと任意でワークスペースのユーザーを担当に選べる（または担当者なし）。 -->
      <DropdownMenu.Root>
        <DropdownMenu.Trigger>
          {#snippet child({ props })}
            <Button {...props} class="mt-auto w-fit gap-1.5" variant="outline" size="sm" disabled={busy}>
              {m.debt_action_create_issue()}
              <ChevronDown class="size-3.5" />
            </Button>
          {/snippet}
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="start" class="max-h-72 min-w-56 overflow-y-auto">
          <DropdownMenu.Item onSelect={() => createIssue()}>{m.debt_issue_assignee_none()}</DropdownMenu.Item>
          {#if memberList.length}
            <DropdownMenu.Separator />
            <DropdownMenu.Label>{m.debt_issue_assignee_pick()}</DropdownMenu.Label>
            {#each memberList as mem (mem.user_id)}
              <DropdownMenu.Item onSelect={() => createIssue(mem.user_id)}>
                <span class="truncate">{mem.user.display_name ?? mem.user.email}</span>
              </DropdownMenu.Item>
            {/each}
          {/if}
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    {/if}
  </section>
</div>
