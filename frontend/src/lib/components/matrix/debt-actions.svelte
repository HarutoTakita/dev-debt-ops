<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import UserPlus from "@lucide/svelte/icons/user-plus";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import ChevronsUpDown from "@lucide/svelte/icons/chevrons-up-down";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { createDebtIssue, createRepaymentPr, getDebt, getJob, listBranches } from "$lib/api/client";
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
  let prGenerating = $state(false); // 修正 PR を非同期生成中（「生成中…」表示）

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
  const defaultBranchName = $derived(branches.find((b) => b.is_default)?.name ?? "");
  // アプリ標準のドロップダウン Trigger 用クラス（設定ページ等と共通）。
  const triggerClass =
    "flex h-9 items-center justify-between gap-2 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none";

  // プレビュー用の派生値。
  const fileName = $derived(debt.file_path.split("/").pop() ?? debt.file_path);
  const headBranch = $derived(`devdebtops/fix-${debt.id.slice(0, 8)}`);
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

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // 修正 PR ジョブ（非同期）を完了まで待ち、生成された PR の URL を返す。失敗時は例外。
  async function pollPrJob(jobId: string): Promise<string | null> {
    for (let i = 0; i < 90; i++) {
      const job = await getJob(jobId);
      if (job.status === "COMPLETED") {
        const updated = await getDebt(orgSlug, projectSlug, debt.id);
        return updated.kind === "code" ? (updated.related_pr ?? null) : null;
      }
      if (job.status === "FAILED" || job.status === "CANCELLED") {
        throw new Error(job.error ?? m.common_error_generic());
      }
      await sleep(2000);
    }
    return null; // タイムアウト（生成が長い）。セクションの再読込で後追い表示される。
  }

  function openLink(url: string) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  // 進行中の修正 PR ジョブ id を debt 単位で localStorage に保存し、リロードしても「生成中…」を復元する。
  const JOBS_KEY = "devdebtops:repay-jobs";
  function readJobs(): Record<string, string> {
    if (typeof localStorage === "undefined") return {};
    try {
      return JSON.parse(localStorage.getItem(JOBS_KEY) ?? "{}") as Record<string, string>;
    } catch {
      return {};
    }
  }
  function writeJob(debtId: string, jobId: string | null) {
    if (typeof localStorage === "undefined") return;
    const jobs = readJobs();
    if (jobId) jobs[debtId] = jobId;
    else delete jobs[debtId];
    localStorage.setItem(JOBS_KEY, JSON.stringify(jobs));
  }

  // ジョブを「生成中…」表示でポーリングし、完了で PR リンク通知 + 永続状態をクリアする。
  // notifySuccess: 成功トーストを出すか（復元時は抑制）。失敗は復元時も含めて常に通知する。
  async function runPoll(jobId: string, notifySuccess: boolean) {
    prGenerating = true;
    try {
      const url = await pollPrJob(jobId);
      writeJob(debt.id, null);
      await invalidateAll();
      if (notifySuccess) {
        if (url)
          toast.success(m.debt_pr_created(), { action: { label: m.debt_open_pr(), onClick: () => openLink(url) } });
        else toast.success(m.debt_pr_created());
      }
    } catch (e) {
      // 失敗（GitHub 403・権限不足など）はリロード復元時でも必ず可視化する。
      writeJob(debt.id, null);
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      prGenerating = false;
    }
  }

  // リロード復元: 進行中ジョブが残っていれば（かつ未完了なら）ポーリングを再開する。debt 単位で 1 回だけ。
  let resumedFor = $state<string | null>(null);
  $effect(() => {
    const id = debt.id;
    const done = relatedPr;
    if (resumedFor === id) return;
    resumedFor = id;
    if (done) {
      writeJob(id, null);
      return;
    }
    const jobId = readJobs()[id];
    if (jobId) void runPoll(jobId, false);
  });

  async function confirmPr() {
    busy = true;
    try {
      const job = await createRepaymentPr(orgSlug, projectSlug, debt.id, baseBranch || undefined);
      prOpen = false;
      writeJob(debt.id, job.job_id); // リロードでも復元できるよう永続化
      toast.info(m.debt_repayment_pr_started());
      void runPoll(job.job_id, true); // 非ブロッキング。完了したらリンク通知
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }

  async function confirmIssue() {
    busy = true;
    try {
      const updated = await createDebtIssue(orgSlug, projectSlug, debt.id, assigneeUserId || undefined);
      issueOpen = false;
      await invalidateAll();
      const url = updated.kind === "code" ? updated.related_issue : null;
      if (url)
        toast.success(m.debt_issue_created(), {
          action: { label: m.debt_open_issue(), onClick: () => openLink(url) },
        });
      else toast.success(m.debt_issue_created());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : m.common_error_generic());
    } finally {
      busy = false;
    }
  }
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
    {:else if prGenerating}
      <span class="mt-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <LoaderCircle class="size-3.5 animate-spin" />
        {m.debt_pr_generating()}
      </span>
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
        <dd>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger class={`${triggerClass} w-48`} aria-label={m.debt_pr_base_label()}>
              <span class="truncate">{baseBranch}{defaultBranchName === baseBranch ? " (default)" : ""}</span>
              <ChevronsUpDown class="size-4 shrink-0 opacity-50" />
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end" class="max-h-72 min-w-48 overflow-y-auto">
              <DropdownMenu.RadioGroup bind:value={baseBranch}>
                {#each branchNames as b (b)}
                  <DropdownMenu.RadioItem value={b}
                    >{b}{defaultBranchName === b ? " (default)" : ""}</DropdownMenu.RadioItem
                  >
                {/each}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
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
        <DropdownMenu.Root>
          <DropdownMenu.Trigger class={`${triggerClass} w-56`} aria-label={m.debt_issue_field_assignee()}>
            <span class="truncate">{assigneeLabel || m.debt_issue_assignee_unset()}</span>
            <ChevronsUpDown class="size-4 shrink-0 opacity-50" />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end" class="max-h-72 min-w-56 overflow-y-auto">
            <DropdownMenu.RadioGroup bind:value={assigneeUserId}>
              <DropdownMenu.RadioItem value="">{m.debt_issue_assignee_unset()}</DropdownMenu.RadioItem>
              {#each memberList as mem (mem.user_id)}
                <DropdownMenu.RadioItem value={mem.user_id}
                  >{mem.user.display_name ?? mem.user.email}</DropdownMenu.RadioItem
                >
              {/each}
            </DropdownMenu.RadioGroup>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
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
