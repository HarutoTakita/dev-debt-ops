<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { listOrgs } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";
  import { Button } from "$lib/components/ui/button";
  import * as m from "$lib/paraglide/messages";

  // 認証済みなら既定 org のダッシュボードへ自動リダイレクト（callback と同じ解決ロジック）。
  onMount(async () => {
    await auth.init();
    if (!auth.isAuthenticated) return;
    try {
      const orgs = await listOrgs();
      const defaultOrg = orgs.find((o) => o.is_personal) ?? orgs[0];
      if (defaultOrg) goto(resolve(`/${defaultOrg.slug}`));
    } catch {
      /* 失敗時はランディングのまま（CTA から手動でログインへ） */
    }
  });
</script>

<svelte:head>
  <title>DevDebtOps</title>
</svelte:head>

<div class="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
  <div class="space-y-3">
    <h1 class="text-4xl font-bold">DevDebtOps</h1>
    <p class="max-w-md text-lg text-muted-foreground">{m.root_tagline()}</p>
  </div>
  <Button href={resolve("/login")}>{m.root_cta_signin()}</Button>
</div>
