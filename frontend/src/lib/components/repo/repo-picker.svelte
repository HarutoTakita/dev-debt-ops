<script lang="ts">
  import { AppNotInstalledError, listRepositories } from "$lib/api/client";
  import type { Repository } from "$lib/api/schemas";

  type Props = {
    onselect: (repo: Repository) => void;
  };

  const { onselect }: Props = $props();

  type PickerState = "loading" | "ready" | "error" | "not_installed";

  let pickerState: PickerState = $state("loading");
  let repos: Repository[] = $state([]);
  let filter = $state("");
  let page = $state(1);
  let hasMore = $state(false);
  let errorMessage = $state("");
  let appSlug = $state("");

  const filtered = $derived(
    filter.trim() ? repos.filter((r) => r.full_name.toLowerCase().includes(filter.trim().toLowerCase())) : repos,
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
        errorMessage = err instanceof Error ? err.message : "エラーが発生しました";
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
    <div class="text-sm text-muted-foreground">リポジトリを読み込み中...</div>
  {:else if pickerState === "error"}
    <div class="flex flex-col items-center gap-3">
      <p class="text-sm text-destructive">{errorMessage}</p>
      <button onclick={() => load(1)} class="rounded-md border px-4 py-2 text-sm hover:bg-accent"> 再試行 </button>
    </div>
  {:else if pickerState === "not_installed"}
    <div class="flex flex-col items-center gap-4 text-center">
      <p class="text-sm text-muted-foreground">GitHub App がインストールされていません。</p>
      {#if appSlug}
        <a
          href="https://github.com/apps/{appSlug}/installations/new"
          target="_blank"
          rel="noopener noreferrer"
          class="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          GitHub App をインストール
        </a>
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
