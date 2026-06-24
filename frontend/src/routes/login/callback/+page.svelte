<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { listOrgs } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";
  import Logo from "$lib/components/logo.svelte";
  import * as m from "$lib/paraglide/messages";

  // 失敗を分類して、それぞれ異なる文言と復旧導線を出す（握りつぶさず console.error も残す）。
  type ErrorKind = "oauth_denied" | "session" | "no_org" | "dashboard";
  let errorKind = $state<ErrorKind | null>(null);

  const errorText = $derived(
    errorKind === "oauth_denied"
      ? m.auth_error_oauth_denied()
      : errorKind === "no_org"
        ? m.auth_error_no_org()
        : errorKind === "dashboard"
          ? m.auth_error_dashboard()
          : m.auth_error_session(),
  );

  async function run() {
    errorKind = null;

    // GitHub からの認可拒否（access_denied 等）を最優先で検出する。
    const oauthError = page.url.searchParams.get("error");
    if (oauthError) {
      console.error("github oauth error:", oauthError, page.url.searchParams.get("error_description"));
      errorKind = "oauth_denied";
      return;
    }

    const code = page.url.searchParams.get("code");
    const state = page.url.searchParams.get("state");

    if (code && state) {
      const res = await fetch(
        `/api/v1/auth/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
        { credentials: "include" },
      );
      if (!res.ok) {
        console.error("github callback failed:", res.status);
        errorKind = "session";
        return;
      }
    }

    await auth.init();
    if (!auth.isAuthenticated) {
      console.error("session not established after callback");
      errorKind = "session";
      return;
    }

    try {
      const orgs = await listOrgs();
      const defaultOrg = orgs.find((o) => o.is_personal) ?? orgs[0];
      if (defaultOrg) {
        goto(resolve(`/${defaultOrg.slug}`));
      } else {
        errorKind = "no_org";
      }
    } catch (err) {
      console.error("listOrgs failed:", err);
      errorKind = "dashboard";
    }
  }

  onMount(run);
</script>

<svelte:head>
  <title>{m.auth_signing_in()} · DevDebtOps</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center p-6">
  {#if errorKind}
    <div class="flex max-w-sm flex-col items-center gap-3 rounded-lg border bg-card p-6 text-center shadow-sm">
      <Logo class="size-8 text-debt-knowledge" />
      <p class="text-sm font-medium text-destructive">{errorText}</p>
      <div class="mt-1 flex items-center gap-2">
        {#if errorKind === "dashboard"}
          <button onclick={run} class="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
            {m.common_retry()}
          </button>
        {/if}
        <a href={resolve("/login")} class="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
          {m.auth_back_to_login()}
        </a>
      </div>
    </div>
  {:else}
    <p class="text-sm text-muted-foreground">{m.auth_signing_in()}</p>
  {/if}
</div>
