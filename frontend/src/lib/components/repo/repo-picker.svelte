<script lang="ts">
  import { AppNotInstalledError, listRepositories } from "$lib/api/client";
  import type { Repository } from "$lib/api/schemas";
  import { resolve } from "$app/paths";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import * as m from "$lib/paraglide/messages";

  type Props = {
    onselect: (repo: Repository) => void;
  };

  const { onselect }: Props = $props();

  type PickerState = "loading" | "ready" | "error" | "not_installed";
  type ErrorKind = "network" | "auth" | "server";

  let pickerState: PickerState = $state("loading");
  let errorKind = $state<ErrorKind>("server");
  let repos: Repository[] = $state([]);
  let filter = $state("");
  let page = $state(1);
  let hasMore = $state(false);
  let appSlug = $state("");

  const skeletonRows = Array.from({ length: 6 }, (_v, i) => i);

  const filtered = $derived(
    filter.trim() ? repos.filter((r) => r.full_name.toLowerCase().includes(filter.trim().toLowerCase())) : repos,
  );

  // status code を持たないため message から network/auth/server を推定する（ベストエフォート）。
  function classifyError(err: unknown): ErrorKind {
    const msg = err instanceof Error ? err.message : "";
    if (/network|failed to fetch|load failed|networkerror/i.test(msg)) return "network";
    if (/401|403|unauth|認証|セッション/i.test(msg)) return "auth";
    return "server";
  }

  const errorMessage = $derived(
    errorKind === "network"
      ? m.repo_error_network()
      : errorKind === "auth"
        ? m.repo_error_auth()
        : m.repo_error_server(),
  );

  async function load(nextPage = 1) {
    pickerState = "loading";
    try {
      const result = await listRepositories(nextPage, 30);
      if (nextPage === 1) {
        repos = result.repositories;
      } else {
        repos = [...repos, ...result.repositories];
      }
      page = nextPage;
      hasMore = result.has_more;
      pickerState = "ready";
    } catch (err) {
      if (err instanceof AppNotInstalledError) {
        appSlug = err.appSlug;
        pickerState = "not_installed";
      } else {
        console.error("repo-picker load failed", err);
        errorKind = classifyError(err);
        pickerState = "error";
      }
    }
  }

  $effect(() => {
    load(1);
  });
</script>

<div class="flex flex-col items-center gap-6 p-8">
  <div class="text-center">
    <h2 class="text-xl font-semibold">リポジトリを選択</h2>
    <p class="mt-1 text-sm text-muted-foreground">接続するリポジトリを選んでください</p>
  </div>

  {#if pickerState === "loading"}
    <ul class="w-full max-w-lg divide-y rounded-md border" aria-busy="true">
      {#each skeletonRows as i (i)}
        <li class="flex items-center justify-between px-4 py-3">
          <Skeleton class="h-4 w-48" />
          <Skeleton class="h-3 w-16" />
        </li>
      {/each}
    </ul>
  {:else if pickerState === "error"}
    <div class="flex flex-col items-center gap-3 text-center">
      <p class="text-sm text-destructive">{errorMessage}</p>
      {#if errorKind === "auth"}
        <a href={resolve("/login")} class="rounded-md border px-4 py-2 text-sm hover:bg-accent">
          {m.repo_error_login()}
        </a>
      {:else}
        <button onclick={() => load(1)} class="rounded-md border px-4 py-2 text-sm hover:bg-accent">
          {m.common_retry()}
        </button>
      {/if}
    </div>
  {:else if pickerState === "not_installed"}
    <div class="flex flex-col items-center gap-4 text-center">
      <p class="text-sm text-muted-foreground">{m.repo_not_installed()}</p>
      <!-- appSlug があれば直接インストール、無ければ汎用導線とガイダンスを必ず出す（消失させない）。 -->
      {#if appSlug}
        <a
          href="https://github.com/apps/{appSlug}/installations/new"
          target="_blank"
          rel="noopener noreferrer"
          class="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          {m.repo_install_cta()}
        </a>
      {:else}
        <a
          href="https://github.com/apps"
          target="_blank"
          rel="noopener noreferrer"
          class="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          {m.repo_install_browse()}
        </a>
        <p class="text-xs text-muted-foreground">{m.repo_install_ask_admin()}</p>
      {/if}
    </div>
  {:else}
    <div class="w-full max-w-lg">
      <input
        type="search"
        bind:value={filter}
        placeholder="リポジトリを検索..."
        class="mb-3 w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
      />

      {#if filtered.length === 0}
        <p class="py-4 text-center text-sm text-muted-foreground">
          {repos.length === 0 ? "アクセス可能なリポジトリがありません" : "一致するリポジトリがありません"}
        </p>
      {:else}
        <ul class="divide-y rounded-md border">
          {#each filtered as r (r.full_name)}
            <li>
              <button
                onclick={() => onselect(r)}
                class="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-accent"
              >
                <div>
                  <span class="text-sm font-medium">{r.full_name}</span>
                  {#if r.private}
                    <span class="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs">Private</span>
                  {/if}
                </div>
                <span class="text-xs text-muted-foreground">
                  {new Date(r.updated_at).toLocaleDateString("ja-JP")}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if hasMore}
        <button onclick={() => load(page + 1)} class="mt-3 w-full rounded-md border py-2 text-sm hover:bg-accent">
          もっと見る
        </button>
      {/if}
    </div>
  {/if}
</div>
