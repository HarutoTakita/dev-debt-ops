<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { listOrgs } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";

  let error = $state("");

  onMount(async () => {
    const code = page.url.searchParams.get("code");
    const state = page.url.searchParams.get("state");

    if (code && state) {
      // バックエンドの callback を fetch で叩く（204 + Set-Cookie が返る）
      const res = await fetch(
        `/api/v1/auth/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
        { credentials: "include" },
      );
      if (!res.ok) {
        error = "サインインに失敗しました。もう一度お試しください。";
        return;
      }
      // Cookie がセットされた状態で続行
    }

    // 認証確認 → org ダッシュボードへ
    await auth.init();

    if (!auth.isAuthenticated) {
      error = "サインインに失敗しました。もう一度お試しください。";
      return;
    }

    try {
      const orgs = await listOrgs();
      const defaultOrg = orgs.find((o) => o.is_personal) ?? orgs[0];
      if (defaultOrg) {
        goto(resolve(`/${defaultOrg.slug}`));
      } else {
        error = "組織が見つかりませんでした。";
      }
    } catch {
      error = "ダッシュボードへの遷移に失敗しました。";
    }
  });
</script>

<svelte:head>
  <title>サインイン中... · Rosetta</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center">
  {#if error}
    <div class="text-center">
      <p class="text-destructive">{error}</p>
      <a href={resolve("/login")} class="mt-4 block text-sm text-muted-foreground hover:underline">
        ログイン画面に戻る
      </a>
    </div>
  {:else}
    <p class="text-sm text-muted-foreground">サインイン中...</p>
  {/if}
</div>
