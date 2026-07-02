<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { apiFetch, demoLogin, getPublicConfig, listOrgs } from "$lib/api/client";
  import { auth } from "$lib/stores/auth.svelte";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import LoginGraphCanvas from "$lib/components/auth/login-graph-canvas.svelte";

  let loading = $state(false);
  let demoEnabled = $state(false);
  let demoLoading = $state(false);
  let demoError = $state(false);

  onMount(async () => {
    try {
      demoEnabled = (await getPublicConfig()).demo_mode_enabled;
    } catch {
      demoEnabled = false;
    }
  });

  async function signIn() {
    loading = true;
    try {
      const res = await apiFetch("/api/v1/auth/github/authorize");
      const data = await res.json();
      window.location.href = data.authorization_url;
    } catch {
      loading = false;
    }
  }

  // GitHub なしでゲストデモにログインし、シード済みデモ org のダッシュボードへ遷移する（issue 069）。
  async function startDemo() {
    demoLoading = true;
    demoError = false;
    try {
      await demoLogin();
      await auth.init();
      const orgs = await listOrgs();
      const target = orgs[0];
      if (target) {
        goto(resolve(`/${target.slug}`));
        return;
      }
      demoError = true;
    } catch {
      demoError = true;
    }
    demoLoading = false;
  }
</script>

<svelte:head>
  <title>サインイン · DevDebtOps</title>
</svelte:head>

<div class="relative flex min-h-screen flex-col items-center justify-center gap-8 overflow-hidden p-8">
  <!-- 背景: 動くノード‐リンクグラフ（参考LP 参照）。中身は z-10 で前面に出す。 -->
  <LoginGraphCanvas />

  <div class="relative z-10 text-center">
    <h1 class="text-3xl font-bold text-slate-50">DevDebtOps</h1>
    <p class="mt-2 text-sm text-slate-400">コード品質とチーム理解度の可視化</p>
  </div>

  <div class="relative z-10 flex flex-col items-center gap-3">
    <button
      onclick={signIn}
      disabled={loading}
      class="inline-flex items-center gap-3 rounded-lg bg-white px-6 py-3 font-medium text-slate-900 shadow-lg transition-colors hover:bg-slate-100 disabled:opacity-50"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path
          d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        />
      </svg>
      {loading ? "リダイレクト中..." : "GitHub でサインイン"}
    </button>

    {#if demoEnabled}
      <Tooltip.Provider>
        <Tooltip.Root>
          <Tooltip.Trigger>
            {#snippet child({ props })}
              <button
                {...props}
                onclick={startDemo}
                disabled={demoLoading}
                class="inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-6 py-3 text-sm font-medium text-slate-100 backdrop-blur-sm transition-colors hover:bg-white/10 disabled:opacity-50"
              >
                {demoLoading ? "準備中..." : "お試しはこちら"}
              </button>
            {/snippet}
          </Tooltip.Trigger>
          <Tooltip.Content class="max-w-xs text-center">
            GitHub アカウントなしで、サンプルプロジェクトをすぐに体験できます。
          </Tooltip.Content>
        </Tooltip.Root>
      </Tooltip.Provider>
      {#if demoError}
        <p class="text-xs text-red-400">デモの開始に失敗しました。時間をおいて再度お試しください。</p>
      {/if}
    {/if}
  </div>
</div>
