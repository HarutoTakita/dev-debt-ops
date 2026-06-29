<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import UserPlus from "@lucide/svelte/icons/user-plus";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Dialog from "$lib/components/ui/dialog";
  import { createDebtIssue, createRepaymentPr, listBranches } from "$lib/api/client";
  import type { Branch, DebtItem } from "$lib/api/schemas";
  import { members } from "$lib/stores/members-store.svelte";
  import { repo } from "$lib/stores/repo-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード負債への 2 つの対応経路（issue 210/215）。どちらも作成前に確認モーダルを出す:
  //   AI に頼む  = 修正 PR を自動生成（Gemini が修正案、issue 033）。PR 先ブランチを選べる。
  //   人に頼む    = GitHub Issue を作成（任意でワークスペースのユーザーを担当に指定）。
  type Props = { orgSlug: string; projectSlug: string; debt: DebtItem };
  const { orgSlug, projectSlug, debt }: Props = $props();

  // related_pr / related_issue は code 負債のみ。knowledge 負債では undefined。
  const relatedPr = $derived(debt.kind === "code" ? debt.related_pr : null);
  const relatedIssue = $derived(debt.kind === "code" ? debt.related_issue : null);

  let busy = $state(false);
  let prOpen = $state(false);
  let issueOpen = $state(false);

  // 担当候補（ワークスペースのメンバー）。
  $effect(() => {
    if (orgSlug) void members.load(orgSlug);
  });
  const memberList = $derived(members.members);
  let assigneeUserId = $state(""); // "" = 担当者なし

  // PR 先（base）ブランチ候補。プロジェクトのリポジトリから取得。
  let branches = $state<Branch[]>([]);
  let baseBranch = $state("");
  $effect(() => {
    const c = repo.connected;
    if (!c) return;
    baseBranch = c.default_branch;
    void listBranches(c.owner, c.name)
      .then((r) => (branches = r.branches))
      .catch(() => (branches = []));
  });
  const branchNames = $derived.by(() => {
    const names = branches.map((b) => b.name);
    return !baseBranch || names.includes(baseBranch) ? names : [baseBranch, ...names];
  });

  // プレビュー用の派生値。
  const fileName = $derived(debt.file_path.split("/").pop() ?? debt.file_path);
  const headBranch = $derived(`rosetta/repay-${debt.id.slice(0, 8)}`);
  const prTitle = $derived(`[修正] ${fileName} を改善`);
  const assigneeLabel = $derived(
    assigneeUserId
      ? (memberList.find((mem) => mem.user_id === assigneeUserId)?.user.display_name ??
          memberList.find((mem) => mem.user_id === assigneeUserId)?.user.email ??
          "")
      : "",
  );

  // 人に頼む Issue 本文プレビュー（backend の _issue_body に対応）。
  const issueTitle = $derived(
    debt.kind === "code" ? `[技術負債] ${debt.file_path} の${debt.type}（${debt.severity}）` : debt.file_path,
  );
  const issueBody = $derived.by(() => {
    if (debt.kind !== "code") return debt.file_path;
    const lines = [
      `## 技術負債: ${debt.file_path}`,
      "",
      `- 種別: ${debt.type}`,
      `- 深刻度: ${debt.severity}`,
      `- 推定修正工数: 約 ${debt.estimated_repay_hours} 時間`,
      `- 理解度(KC): ${Math.round(debt.knowledge_coverage * 100)}%`,
    ];
    if (assigneeLabel) lines.push(`- 担当: ${assigneeLabel}`);
    lines.push("", "### 検知根拠", debt.archaeology_notes || "（記録なし）");
    return lines.join("\n");
  });

  async function confirmPr() {
    busy = true;
    try {
      await createRepaymentPr(orgSlug, projectSlug, debt.id, baseBranch || undefined);
      toast.success(m.debt_repayment_pr_started());
      prOpen = false;
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }

  async function confirmIssue() {
    busy = true;
    try {
      await createDebtIssue(orgSlug, projectSlug, debt.id, assigneeUserId || undefined);
      toast.success(m.debt_issue_created());
      issueOpen = false;
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }

  const selectClass =
    "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none";
</script>

<div class="grid gap-3 sm:grid-cols-2">
  <!-- AI に頼む: 修正 PR を自動生成 -->
  <section class="flex flex-col gap-2 rounded-lg border bg-card p-3">
    <div class="flex items-center gap-1.5 text-sm font-medium">
      <Bot class="size-4 text-debt-knowledge" />
      {m.debt_path_ai_title()}
    </div>
    <p class="text-xs text-muted-foreground">{m.debt_path_ai_desc()}</p>
    {#if relatedPr}
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
      <Button class="mt-auto w-fit" variant="outline" size="sm" disabled={busy} onclick={() => (prOpen = true)}>
        {m.debt_action_create_pr()}
      </Button>
    {/if}
  </section>

  <!-- 人に頼む: GitHub Issue を作成 -->
  <section class="flex flex-col gap-2 rounded-lg border bg-card p-3">
    <div class="flex items-center gap-1.5 text-sm font-medium">
      <UserPlus class="size-4 text-debt-code" />
      {m.debt_path_human_title()}
    </div>
    <p class="text-xs text-muted-foreground">{m.debt_path_human_desc()}</p>
    {#if relatedIssue}
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
      <Button class="mt-auto w-fit" variant="outline" size="sm" disabled={busy} onclick={() => (issueOpen = true)}>
        {m.debt_action_create_issue()}
      </Button>
    {/if}
  </section>
</div>

<!-- 修正 PR 確認モーダル -->
<Dialog.Root bind:open={prOpen}>
  <Dialog.Content class="sm:max-w-lg">
    <Dialog.Header>
      <Dialog.Title>{m.debt_confirm_title()}</Dialog.Title>
    </Dialog.Header>
    <dl class="flex flex-col gap-2 text-sm">
      <div class="flex justify-between gap-3">
        <dt class="shrink-0 text-muted-foreground">{m.debt_pr_field_target()}</dt>
        <dd class="truncate text-right font-mono text-xs">{debt.file_path}</dd>
      </div>
      <div class="flex items-center justify-between gap-3">
        <dt class="shrink-0 text-muted-foreground">{m.debt_pr_base_label()}</dt>
        <dd class="w-48">
          <select bind:value={baseBranch} class={selectClass} aria-label={m.debt_pr_base_label()}>
            {#each branchNames as b (b)}
              <option value={b}>{b}</option>
            {/each}
          </select>
        </dd>
      </div>
      <div class="flex justify-between gap-3">
        <dt class="shrink-0 text-muted-foreground">{m.debt_pr_field_head()}</dt>
        <dd class="truncate text-right font-mono text-xs">{headBranch}</dd>
      </div>
      <div class="flex justify-between gap-3">
        <dt class="shrink-0 text-muted-foreground">{m.debt_pr_field_title()}</dt>
        <dd class="text-right">{prTitle}</dd>
      </div>
    </dl>
    <p class="rounded-md bg-muted/50 p-2.5 text-xs text-muted-foreground">{m.debt_pr_ai_note()}</p>
    <Dialog.Footer>
      <Button variant="ghost" disabled={busy} onclick={() => (prOpen = false)}>{m.debt_confirm_cancel()}</Button>
      <Button disabled={busy || !baseBranch} onclick={confirmPr}>{m.debt_confirm_create()}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<!-- GitHub Issue 確認モーダル -->
<Dialog.Root bind:open={issueOpen}>
  <Dialog.Content class="sm:max-w-lg">
    <Dialog.Header>
      <Dialog.Title>{m.debt_confirm_title()}</Dialog.Title>
    </Dialog.Header>
    <div class="flex flex-col gap-3 text-sm">
      <div class="flex items-center justify-between gap-3">
        <span class="shrink-0 text-muted-foreground">{m.debt_issue_field_assignee()}</span>
        <select bind:value={assigneeUserId} class={`${selectClass} w-56`} aria-label={m.debt_issue_field_assignee()}>
          <option value="">{m.debt_issue_assignee_unset()}</option>
          {#each memberList as mem (mem.user_id)}
            <option value={mem.user_id}>{mem.user.display_name ?? mem.user.email}</option>
          {/each}
        </select>
      </div>
      <div>
        <div class="text-muted-foreground">{m.debt_issue_field_title()}</div>
        <div class="mt-1 font-medium">{issueTitle}</div>
      </div>
      <div>
        <div class="text-muted-foreground">{m.debt_issue_field_body()}</div>
        <pre
          class="mt-1 max-h-56 overflow-auto rounded-md border bg-muted/40 p-2.5 text-xs whitespace-pre-wrap">{issueBody}</pre>
      </div>
    </div>
    <Dialog.Footer>
      <Button variant="ghost" disabled={busy} onclick={() => (issueOpen = false)}>{m.debt_confirm_cancel()}</Button>
      <Button disabled={busy} onclick={confirmIssue}>{m.debt_confirm_create()}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
