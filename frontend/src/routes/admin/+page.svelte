<script lang="ts">
  import { onMount } from "svelte";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Shield from "@lucide/svelte/icons/shield";
  import Users from "@lucide/svelte/icons/users";
  import GraduationCap from "@lucide/svelte/icons/graduation-cap";
  import GitPullRequest from "@lucide/svelte/icons/git-pull-request";
  import CircleDot from "@lucide/svelte/icons/circle-dot";
  import { toast } from "svelte-sonner";
  import { resolve } from "$app/paths";
  import { listUserActivity, grantUserCredits } from "$lib/api/client";
  import type { UserActivity } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import { auth } from "$lib/stores/auth.svelte";
  import { getLocale } from "$lib/paraglide/runtime";
  import * as m from "$lib/paraglide/messages";

  // 業務管理ダッシュボード（superuser 限定。ガードは +page.ts）。メンバーの学習・テスト・PR/Issue・
  // 最終アクティブを俯瞰し、解析クレジットを付与する。1 エンドポイント（/users/activity）で全列を賄う。
  let rows = $state<UserActivity[]>([]);
  let loading = $state(true);
  let error = $state(false);
  let query = $state("");
  // 行ごとの付与入力額と処理中フラグ（user id 単位）。
  let amounts = $state<Record<string, number>>({});
  let busy = $state<Record<string, boolean>>({});

  const filtered = $derived(
    rows.filter((u) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return u.email.toLowerCase().includes(q) || (u.display_name ?? "").toLowerCase().includes(q);
    }),
  );

  // サマリー合計（フィルタ後の対象で集計）。
  const summary = $derived({
    members: filtered.length,
    quizzes: filtered.reduce((n, u) => n + u.quiz_completed, 0),
    prs: filtered.reduce((n, u) => n + u.pr_count, 0),
    issues: filtered.reduce((n, u) => n + u.issue_count, 0),
  });

  onMount(async () => {
    try {
      rows = await listUserActivity();
    } catch {
      error = true;
    } finally {
      loading = false;
    }
  });

  function learningPct(u: UserActivity): number {
    return u.learning_steps_total > 0 ? Math.round((u.learning_steps_completed / u.learning_steps_total) * 100) : 0;
  }

  function quizAvg(u: UserActivity): number | null {
    return u.quiz_avg_score != null ? Math.round(u.quiz_avg_score * 100) : null;
  }

  function quizPct(u: UserActivity): number {
    return u.quiz_total > 0 ? Math.round((u.quiz_completed / u.quiz_total) * 100) : 0;
  }

  // 最終アクティブをロケール依存の相対時刻で表示（未ログインは "—" 相当）。
  function lastActive(iso?: string | null): string {
    if (!iso) return m.admin_never_active();
    const then = new Date(iso).getTime();
    const diff = then - Date.now();
    const abs = Math.abs(diff);
    const min = 60_000;
    const hr = 3_600_000;
    const day = 86_400_000;
    const rtf = new Intl.RelativeTimeFormat(getLocale(), { numeric: "auto" });
    if (abs < hr) return rtf.format(Math.round(diff / min), "minute");
    if (abs < day) return rtf.format(Math.round(diff / hr), "hour");
    if (abs < 30 * day) return rtf.format(Math.round(diff / day), "day");
    return new Intl.DateTimeFormat(getLocale(), { dateStyle: "medium" }).format(then);
  }

  // クレジットを増減する。sign=1 で付与、sign=-1 で減算（サーバ側で残高は 0 未満にならないようクランプ）。
  async function adjust(u: UserActivity, sign: 1 | -1) {
    const amount = amounts[u.id] ?? 5;
    if (!Number.isFinite(amount) || amount < 1) {
      toast.error(m.admin_grant_invalid());
      return;
    }
    const magnitude = Math.floor(amount);
    busy = { ...busy, [u.id]: true };
    try {
      const updated = await grantUserCredits(u.id, magnitude * sign);
      rows = rows.map((x) => (x.id === u.id ? { ...x, analysis_credits: updated.analysis_credits } : x));
      const args = { email: u.email, amount: magnitude, balance: updated.analysis_credits };
      toast.success(sign > 0 ? m.admin_grant_success(args) : m.admin_reduce_success(args));
    } catch {
      toast.error(sign > 0 ? m.admin_grant_error() : m.admin_reduce_error());
    } finally {
      busy = { ...busy, [u.id]: false };
    }
  }
</script>

<svelte:head>
  <title>{m.shell_user_admin()} · DevDebtOps</title>
</svelte:head>

{#snippet summaryCard(label: string, value: number, Icon: typeof Users)}
  <div class="flex items-center gap-3 rounded-lg border bg-card p-3">
    <span class="flex size-9 shrink-0 items-center justify-center rounded-md bg-debt-knowledge/15 text-debt-knowledge">
      <Icon class="size-5" />
    </span>
    <div class="min-w-0">
      <div class="text-lg font-semibold leading-none tabular-nums">{value}</div>
      <div class="mt-1 truncate text-xs text-muted-foreground">{label}</div>
    </div>
  </div>
{/snippet}

<div class="mx-auto flex max-w-6xl flex-col gap-4 p-4 sm:p-6">
  <div class="flex flex-wrap items-center gap-2">
    <a href={resolve("/")} class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" />
      {m.common_back_to_app()}
    </a>
  </div>

  <div class="flex items-center gap-2">
    <Shield class="size-5 text-debt-knowledge" />
    <h1 class="font-display text-xl font-semibold">{m.shell_user_admin()}</h1>
  </div>

  {#if !loading && !error}
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {@render summaryCard(m.admin_summary_members(), summary.members, Users)}
      {@render summaryCard(m.admin_summary_quizzes(), summary.quizzes, GraduationCap)}
      {@render summaryCard(m.admin_summary_prs(), summary.prs, GitPullRequest)}
      {@render summaryCard(m.admin_summary_issues(), summary.issues, CircleDot)}
    </div>
  {/if}

  <Input bind:value={query} placeholder={m.admin_search_placeholder()} class="max-w-sm" />

  {#if loading}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_loading()}</p>
  {:else if error}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_load_error()}</p>
  {:else if filtered.length === 0}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_empty()}</p>
  {:else}
    <div class="overflow-x-auto rounded-lg border">
      <table class="w-full text-sm">
        <thead class="border-b bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th class="px-3 py-2 font-medium">{m.admin_col_user()}</th>
            <th class="px-3 py-2 font-medium">{m.field_role()}</th>
            <th class="px-3 py-2 font-medium">{m.admin_col_last_active()}</th>
            <th class="px-3 py-2 font-medium">{m.admin_col_learning()}</th>
            <th class="px-3 py-2 font-medium">{m.admin_col_quiz()}</th>
            <th class="px-3 py-2 text-right font-medium">{m.admin_col_pr()}</th>
            <th class="px-3 py-2 text-right font-medium">{m.admin_col_issue()}</th>
            <th class="px-3 py-2 text-right font-medium">{m.admin_col_credits()}</th>
            <th class="px-3 py-2 font-medium">{m.admin_col_grant()}</th>
          </tr>
        </thead>
        <tbody>
          {#each filtered as u (u.id)}
            {@const pct = learningPct(u)}
            {@const qpct = quizPct(u)}
            {@const avg = quizAvg(u)}
            <tr class="border-b last:border-0">
              <td class="min-w-0 px-3 py-2">
                <div class="truncate font-medium">{u.display_name || u.email}</div>
                {#if u.display_name}<div class="truncate text-xs text-muted-foreground">{u.email}</div>{/if}
              </td>
              <td class="px-3 py-2">
                {#if u.is_superuser}
                  <Badge variant="default">{m.role_admin()}</Badge>
                {:else if u.is_demo}
                  <Badge variant="outline">{m.role_demo()}</Badge>
                {:else}
                  <Badge variant="secondary">{m.role_user()}</Badge>
                {/if}
              </td>
              <td class="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{lastActive(u.last_active_at)}</td>
              <td class="px-3 py-2">
                <div class="flex items-center gap-2">
                  <div class="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted">
                    <div class="h-full rounded-full bg-debt-knowledge" style="width: {pct}%"></div>
                  </div>
                  <span class="text-xs tabular-nums text-muted-foreground">
                    {u.learning_steps_completed}/{u.learning_steps_total}
                  </span>
                </div>
              </td>
              <td class="px-3 py-2">
                <div class="flex items-center gap-2">
                  <div class="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted">
                    <div class="h-full rounded-full bg-debt-knowledge" style="width: {qpct}%"></div>
                  </div>
                  <span class="text-xs tabular-nums text-muted-foreground">
                    {u.quiz_completed}/{u.quiz_total}{avg == null ? "" : ` · ${avg}%`}
                  </span>
                </div>
              </td>
              <td class="px-3 py-2 text-right tabular-nums">{u.pr_count}</td>
              <td class="px-3 py-2 text-right tabular-nums">{u.issue_count}</td>
              <td class="px-3 py-2 text-right font-medium tabular-nums">{u.analysis_credits}</td>
              <td class="px-3 py-2">
                {#if auth.isDemo}
                  <span class="text-xs text-muted-foreground">{m.admin_demo_readonly()}</span>
                {:else}
                  <div class="flex items-center gap-1.5">
                    <Input
                      type="number"
                      min="1"
                      value={amounts[u.id] ?? 5}
                      oninput={(e) => (amounts = { ...amounts, [u.id]: e.currentTarget.valueAsNumber })}
                      class="h-8 w-20"
                    />
                    <Button size="sm" class="h-8" disabled={busy[u.id]} onclick={() => adjust(u, 1)}
                      >{m.admin_grant()}</Button
                    >
                    <Button size="sm" variant="outline" class="h-8" disabled={busy[u.id]} onclick={() => adjust(u, -1)}
                      >{m.admin_reduce()}</Button
                    >
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
