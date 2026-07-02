<script lang="ts">
  import { onMount } from "svelte";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import CircleUser from "@lucide/svelte/icons/circle-user";
  import { resolve } from "$app/paths";
  import { auth } from "$lib/stores/auth.svelte";
  import { Badge } from "$lib/components/ui/badge";

  // アカウント画面（ログイン済みの全ユーザー）。残りの解析クレジットを確認できる（ガードは +page.ts）。
  const user = $derived(auth.user);
  const roleLabel = $derived(auth.isAdmin ? "管理者" : auth.isDemo ? "デモ" : "一般ユーザー");

  onMount(() => {
    void auth.refreshUser(); // 管理者付与後などの最新残高を反映
  });
</script>

<svelte:head>
  <title>アカウント · DevDebtOps</title>
</svelte:head>

<div class="mx-auto flex max-w-xl flex-col gap-4 p-4 sm:p-6">
  <a href={resolve("/")} class="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
    <ArrowLeft class="size-4" />
    アプリに戻る
  </a>

  <div class="flex items-center gap-2">
    <CircleUser class="size-5 text-debt-knowledge" />
    <h1 class="font-display text-xl font-semibold">アカウント</h1>
  </div>

  <div class="flex flex-col divide-y rounded-lg border">
    <div class="flex items-center justify-between gap-3 px-4 py-3">
      <span class="text-sm text-muted-foreground">メールアドレス</span>
      <span class="min-w-0 truncate text-sm font-medium">{user?.email ?? "—"}</span>
    </div>
    {#if user?.display_name}
      <div class="flex items-center justify-between gap-3 px-4 py-3">
        <span class="text-sm text-muted-foreground">表示名</span>
        <span class="min-w-0 truncate text-sm font-medium">{user.display_name}</span>
      </div>
    {/if}
    <div class="flex items-center justify-between gap-3 px-4 py-3">
      <span class="text-sm text-muted-foreground">ロール</span>
      <Badge variant={auth.isAdmin ? "default" : "secondary"}>{roleLabel}</Badge>
    </div>
    <div class="flex items-center justify-between gap-3 px-4 py-3">
      <span class="text-sm text-muted-foreground">残りの解析クレジット</span>
      {#if auth.creditsEnabled}
        <span class="text-lg font-semibold tabular-nums">{auth.analysisCredits}</span>
      {:else}
        <span class="text-sm font-medium text-muted-foreground">無制限（クレジット無効）</span>
      {/if}
    </div>
  </div>

  {#if auth.creditsEnabled}
    <p class="text-xs leading-relaxed text-muted-foreground">
      解析クレジットは「リポジトリ解析」1 回につき 1
      消費します。残高が不足した場合は、管理者にクレジットの付与を依頼してください。
    </p>
  {/if}
</div>
