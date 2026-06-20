<script lang="ts">
  import { untrack } from "svelte";
  import { listDebts, type DebtFilter, type DebtSort } from "$lib/api/client";
  import type { DebtItem } from "$lib/api/schemas";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import FilteredSearchBar from "$lib/components/filter/filtered-search-bar.svelte";
  import SortControl from "$lib/components/filter/sort-control.svelte";
  import DebtListRow from "$lib/components/matrix/debt-list-row.svelte";
  import { recentSearches } from "$lib/stores/recent-searches.svelte";
  import Logo from "$lib/components/logo.svelte";
  import Skeleton from "$lib/components/ui-ext/skeleton.svelte";
  import { Button } from "$lib/components/ui/button";
  import { analysisRun } from "$lib/stores/analysis-run-store.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  const orgSlug = $derived(data.orgSlug);
  const projectSlug = $derived(data.projectSlug);

  // URL クエリ由来の初期フィルタを一度だけ seed する（以降は state を直接更新）。
  let filter = $state<DebtFilter>(untrack(() => data.initialFilter ?? {}));
  let sort = $state<DebtSort>({ key: "severity", dir: "desc" });
  let debts = $state<DebtItem[]>([]);
  let loading = $state(true);

  const skeletonRows = Array.from({ length: 6 }, (_v, i) => i);

  $effect(() => {
    recentSearches.load(orgSlug);
  });

  // フィルタ/ソート変更で再取得（モック）。filter/sort/orgSlug を読むので変更時に再実行される。
  $effect(() => {
    const f = filter;
    const s = sort;
    loading = true;
    listDebts(orgSlug, projectSlug, f, s)
      .then((res) => {
        debts = res.debts;
        loading = false;
      })
      .catch(() => {
        debts = [];
        loading = false;
      });
  });

  function onfilter(f: DebtFilter) {
    filter = f;
    recentSearches.add(f);
  }
  function onsort(s: DebtSort) {
    sort = s;
  }

  function cellLabel(cell: string | null): string {
    if (!cell) return m.matrix_all_quadrants();
    const map: Record<string, string> = {
      danger: m.overview_quadrant_danger(),
      ideal: m.overview_quadrant_ideal(),
      code_repay: m.overview_quadrant_code_repay(),
      refactor: m.overview_quadrant_refactor(),
    };
    return map[cell] ?? m.matrix_all_quadrants();
  }
</script>

<svelte:head>
  <title>{m.matrix_title()} · Rosetta</title>
</svelte:head>

<div class="mx-auto flex max-w-4xl flex-col gap-3 p-4">
  <div class="flex items-baseline justify-between gap-2">
    <h1 class="font-display text-xl font-semibold">{m.matrix_title()}</h1>
    <span class="text-xs text-muted-foreground">
      {m.matrix_target_quadrant()}: <span class="text-foreground">{cellLabel(data.cell)}</span>
    </span>
  </div>

  <div class="flex flex-col gap-2">
    <FilteredSearchBar {filter} {onfilter} />
    <div class="flex items-center justify-between">
      <span class="text-xs text-muted-foreground">{m.matrix_total({ count: debts.length })}</span>
      <SortControl {sort} {onsort} />
    </div>
  </div>

  {#if loading}
    <!-- レイアウト準拠スケルトン: DebtListRow の形（rounded-lg border bg-card）に合わせたゴースト行 -->
    <ul class="flex flex-col gap-2" aria-busy="true">
      {#each skeletonRows as i (i)}
        <li class="rounded-lg border bg-card p-3">
          <div class="flex items-center gap-3">
            <Skeleton class="h-5 w-12" />
            <Skeleton class="h-4 flex-1" />
            <Skeleton class="h-4 w-16" />
          </div>
          <div class="mt-2 flex items-center gap-4">
            <Skeleton class="h-3 w-24" />
            <Skeleton class="h-3 w-16" />
          </div>
        </li>
      {/each}
    </ul>
  {:else if debts.length === 0}
    <div class="flex flex-col items-center gap-3 py-16 text-center">
      <Logo class="size-10 text-debt-code/70" />
      <p class="text-sm font-medium">{m.matrix_empty()}</p>
      <p class="max-w-sm text-xs text-muted-foreground">{m.matrix_empty_hint()}</p>
      <Button
        disabled={analysisRun.stages.detect_code.status === "QUEUED" ||
          analysisRun.stages.detect_code.status === "PROCESSING"}
        onclick={() => analysisRun.runStage("detect_code", { orgSlug, projectSlug, owner: "", repo: "" })}
      >
        {m.matrix_detect_cta()}
      </Button>
    </div>
  {:else}
    <Tooltip.Provider delayDuration={150}>
      <ul class="flex flex-col gap-2">
        {#each debts as debt (debt.id)}
          <li><DebtListRow {orgSlug} {projectSlug} {debt} /></li>
        {/each}
      </ul>
    </Tooltip.Provider>
  {/if}
</div>
