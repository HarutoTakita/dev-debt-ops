<script lang="ts">
  import { onMount } from "svelte";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Shield from "@lucide/svelte/icons/shield";
  import { toast } from "svelte-sonner";
  import { resolve } from "$app/paths";
  import { listUsers, grantUserCredits } from "$lib/api/client";
  import type { User } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import * as m from "$lib/paraglide/messages";

  // ユーザー管理画面（issue 300・superuser 限定。ガードは +page.ts）。クレジットの付与を行う。
  let users = $state<User[]>([]);
  let loading = $state(true);
  let error = $state(false);
  let query = $state("");
  // 行ごとの付与入力額と処理中フラグ（user id 単位）。
  let amounts = $state<Record<string, number>>({});
  let busy = $state<Record<string, boolean>>({});

  const filtered = $derived(
    users.filter((u) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return u.email.toLowerCase().includes(q) || (u.display_name ?? "").toLowerCase().includes(q);
    }),
  );

  onMount(async () => {
    try {
      users = await listUsers();
    } catch {
      error = true;
    } finally {
      loading = false;
    }
  });

  async function grant(u: User) {
    const amount = amounts[u.id] ?? 5;
    if (!Number.isFinite(amount) || amount < 1) {
      toast.error(m.admin_grant_invalid());
      return;
    }
    busy = { ...busy, [u.id]: true };
    try {
      const updated = await grantUserCredits(u.id, Math.floor(amount));
      users = users.map((x) => (x.id === u.id ? updated : x));
      toast.success(
        m.admin_grant_success({ email: u.email, amount: Math.floor(amount), balance: updated.analysis_credits }),
      );
    } catch {
      toast.error(m.admin_grant_error());
    } finally {
      busy = { ...busy, [u.id]: false };
    }
  }
</script>

<svelte:head>
  <title>{m.shell_user_admin()} · DevDebtOps</title>
</svelte:head>

<div class="mx-auto flex max-w-4xl flex-col gap-4 p-4 sm:p-6">
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
  <p class="text-sm text-muted-foreground">{m.admin_desc()}</p>

  <Input bind:value={query} placeholder={m.admin_search_placeholder()} class="max-w-sm" />

  {#if loading}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_loading()}</p>
  {:else if error}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_load_error()}</p>
  {:else if filtered.length === 0}
    <p class="py-16 text-center text-sm text-muted-foreground">{m.admin_empty()}</p>
  {:else}
    <div class="overflow-hidden rounded-lg border">
      <table class="w-full text-sm">
        <thead class="border-b bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th class="px-3 py-2 font-medium">{m.admin_col_user()}</th>
            <th class="px-3 py-2 font-medium">{m.field_role()}</th>
            <th class="px-3 py-2 text-right font-medium">{m.admin_col_credits()}</th>
            <th class="px-3 py-2 font-medium">{m.admin_col_grant()}</th>
          </tr>
        </thead>
        <tbody>
          {#each filtered as u (u.id)}
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
              <td class="px-3 py-2 text-right font-medium tabular-nums">{u.analysis_credits}</td>
              <td class="px-3 py-2">
                <div class="flex items-center gap-1.5">
                  <Input
                    type="number"
                    min="1"
                    value={amounts[u.id] ?? 5}
                    oninput={(e) => (amounts = { ...amounts, [u.id]: e.currentTarget.valueAsNumber })}
                    class="h-8 w-20"
                  />
                  <Button size="sm" class="h-8" disabled={busy[u.id]} onclick={() => grant(u)}
                    >{m.admin_grant()}</Button
                  >
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
