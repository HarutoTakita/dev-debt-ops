<script lang="ts">
  import { getStack } from "$lib/api/client";
  import type { TechItem, TechStack } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import { StackAnalysisStore } from "$lib/stores/stack-analysis-store.svelte";
  import type { StackStep } from "./stack-trace-steps";
  import { cn } from "$lib/utils";
  import { confidenceBadge } from "./badge-variant";

  type Props = { owner: string; repo: string };
  const { owner, repo }: Props = $props();

  // パネルごとに独立した解析ストア（enqueue + ポーリング）。
  const analysis = new StackAnalysisStore();

  let loadingCache = $state(false);
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

  const STEP_LABELS: Record<StackStep, () => string> = {
    analyzing: m.stack_analyzing,
    listing: m.stack_step_listing,
    reading: m.stack_step_reading,
    classifying: m.stack_step_classifying,
    saving: m.stack_step_saving,
  };

  function highItems(items: TechItem[]): TechItem[] {
    return items.filter((i) => i.confidence === "high");
  }

  function allItems(cats: TechStack["categories"]): { label: string; items: TechItem[] }[] {
    return (Object.entries(CATEGORY_LABELS) as [keyof typeof cats, string][])
      .map(([key, label]) => ({ label, items: cats[key] }))
      .filter(({ items }) => items.length > 0);
  }

  // マウント時は永続化済み結果を読むだけ（解析は実行しない）。
  async function loadCached() {
    loadingCache = true;
    try {
      const cached = await getStack(owner, repo);
      if (cached) analysis.stack = cached;
    } catch {
      /* 未解析なら 404 → null。無視。 */
    } finally {
      loadingCache = false;
    }
  }

  $effect(() => {
    if (owner && repo) void loadCached();
    return () => analysis.cancel();
  });

  const showProgress = $derived(analysis.state === "queued" || analysis.state === "processing");
</script>

<div class="border-b">
  <button
    onclick={() => (open = !open)}
    class="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase hover:bg-accent"
  >
    <span>{m.stack_title()}</span>
    <span>{open ? "▲" : "▼"}</span>
  </button>

  {#if open}
    <div class="px-3 pt-1 pb-3">
      {#if loadingCache && !analysis.stack}
        <p class="text-xs text-muted-foreground">{m.common_loading()}</p>
      {:else if showProgress}
        <!-- 進捗（agent_trace の最新ステップ） -->
        <p class="text-xs text-muted-foreground">
          {analysis.state === "queued" ? m.stack_queued() : STEP_LABELS[analysis.currentStep]()}
        </p>
        {#if analysis.trace.length > 0}
          <p class="mt-1 truncate font-mono text-[10px] text-muted-foreground/70">
            {analysis.trace.at(-1)}
          </p>
        {/if}
      {:else if analysis.state === "error"}
        <p class="mb-2 text-xs text-destructive">{analysis.errorMsg || m.stack_failed()}</p>
        <button onclick={() => analysis.analyze(owner, repo)} class="rounded border px-2 py-1 text-xs hover:bg-accent">
          {m.stack_retry()}
        </button>
      {:else if analysis.stack}
        <div class="space-y-2">
          <!-- 言語 -->
          {#if analysis.stack.languages.length > 0}
            <div>
              <span class="text-xs text-muted-foreground">{m.stack_languages()}</span>
              <div class="mt-1 flex flex-wrap gap-1">
                {#each highItems(analysis.stack.languages).length > 0 ? highItems(analysis.stack.languages) : analysis.stack.languages as lang (lang.name)}
                  <span class={cn("rounded px-1.5 py-0.5 text-xs", confidenceBadge[lang.confidence])}>
                    {lang.name}
                  </span>
                {/each}
              </div>
            </div>
          {/if}
          <!-- カテゴリ別 -->
          {#each allItems(analysis.stack.categories) as { label, items } (label)}
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
              {new Date(analysis.stack.analyzed_at).toLocaleDateString("ja-JP")}
            </span>
            <button
              onclick={() => analysis.analyze(owner, repo)}
              class="text-xs text-muted-foreground underline hover:text-foreground"
            >
              {m.stack_reanalyze()}
            </button>
          </div>
        </div>
      {:else}
        <button
          onclick={() => analysis.analyze(owner, repo)}
          class="w-full rounded border px-2 py-1.5 text-xs hover:bg-accent"
        >
          {m.stack_analyze()}
        </button>
      {/if}
    </div>
  {/if}
</div>
