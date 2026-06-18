<script lang="ts">
  import { analyzeStack, getStack } from "$lib/api/client";
  import type { TechItem, TechStack } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import { confidenceBadge } from "./badge-variant";

  type Props = { owner: string; repo: string };
  const { owner, repo }: Props = $props();

  type PanelState = "idle" | "loading" | "done" | "error";
  let panelState: PanelState = $state("idle");
  let stack = $state<TechStack | null>(null);
  let errorMsg = $state("");
  let open = $state(true);

  const CATEGORY_LABELS: Record<string, string> = {
    frameworks: "FW",
    databases: "DB",
    auth: "Auth",
    container: "Container",
    infra: "Infra",
    cicd: "CI/CD",
    monitoring: "監視",
    testing: "Test",
    other: "Other",
  };

  function highItems(items: TechItem[]): TechItem[] {
    return items.filter((i) => i.confidence === "high");
  }

  function allItems(cats: TechStack["categories"]): { label: string; items: TechItem[] }[] {
    return (Object.entries(CATEGORY_LABELS) as [keyof typeof cats, string][])
      .map(([key, label]) => ({ label, items: cats[key] }))
      .filter(({ items }) => items.length > 0);
  }

  async function load() {
    panelState = "loading";
    try {
      stack = await getStack(owner, repo);
      panelState = stack ? "done" : "idle";
    } catch {
      panelState = "idle";
    }
  }

  async function analyze() {
    panelState = "loading";
    try {
      stack = await analyzeStack(owner, repo);
      panelState = "done";
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : "エラーが発生しました";
      panelState = "error";
    }
  }

  $effect(() => {
    if (owner && repo) load();
  });
</script>

<div class="border-b">
  <button
    onclick={() => (open = !open)}
    class="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase hover:bg-accent"
  >
    <span>テックスタック</span>
    <span>{open ? "▲" : "▼"}</span>
  </button>

  {#if open}
    <div class="px-3 pt-1 pb-3">
      {#if panelState === "loading"}
        <p class="text-xs text-muted-foreground">解析中...</p>
      {:else if panelState === "error"}
        <p class="mb-2 text-xs text-destructive">{errorMsg}</p>
        <button onclick={analyze} class="rounded border px-2 py-1 text-xs hover:bg-accent">再試行</button>
      {:else if panelState === "done" && stack}
        <div class="space-y-2">
          <!-- 言語 -->
          {#if stack.languages.length > 0}
            <div>
              <span class="text-xs text-muted-foreground">言語</span>
              <div class="mt-1 flex flex-wrap gap-1">
                {#each highItems(stack.languages).length > 0 ? highItems(stack.languages) : stack.languages as lang (lang.name)}
                  <span class={cn("rounded px-1.5 py-0.5 text-xs", confidenceBadge[lang.confidence])}>
                    {lang.name}
                  </span>
                {/each}
              </div>
            </div>
          {/if}
          <!-- カテゴリ別 -->
          {#each allItems(stack.categories) as { label, items } (label)}
            <div>
              <span class="text-xs text-muted-foreground">{label}</span>
              <div class="mt-1 flex flex-wrap gap-1">
                {#each items as item (item.name)}
                  <span class={cn("rounded px-1.5 py-0.5 text-xs", confidenceBadge[item.confidence])}>
                    {item.name}
                  </span>
                {/each}
              </div>
            </div>
          {/each}
          <!-- フッター -->
          <div class="flex items-center justify-between pt-1">
            <span class="text-xs text-muted-foreground">
              {new Date(stack.analyzed_at).toLocaleDateString("ja-JP")}
            </span>
            <button onclick={analyze} class="text-xs text-muted-foreground underline hover:text-foreground">
              再解析
            </button>
          </div>
        </div>
      {:else}
        <button onclick={analyze} class="w-full rounded border px-2 py-1.5 text-xs hover:bg-accent"> 解析する </button>
      {/if}
    </div>
  {/if}
</div>
