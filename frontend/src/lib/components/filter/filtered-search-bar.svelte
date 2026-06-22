<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import X from "@lucide/svelte/icons/x";
  import History from "@lucide/svelte/icons/history";
  import type { DebtFilter } from "$lib/api/client";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { recentSearches } from "$lib/stores/recent-searches.svelte";
  import * as m from "$lib/paraglide/messages";

  // GitLab filtered_search_bar_root.vue の写像。種別/深刻度/ステータスをトークン（scope:value ピル）で
  // 多選択フィルタし、最近の検索を localStorage（recent-searches ストア）から復元する。
  type Props = { filter: DebtFilter; onfilter: (f: DebtFilter) => void };
  const { filter, onfilter }: Props = $props();

  type FacetKey = "kind" | "severity" | "status";
  type FacetValue = { value: string; label: () => string };
  type Facet = { key: FacetKey; label: () => string; values: FacetValue[] };

  const FACETS: Facet[] = [
    {
      key: "kind",
      label: m.filter_facet_kind,
      values: [
        { value: "code", label: m.kind_code },
        { value: "knowledge", label: m.kind_knowledge },
      ],
    },
    {
      key: "severity",
      label: m.filter_facet_severity,
      values: [
        { value: "critical", label: m.severity_critical },
        { value: "high", label: m.severity_high },
        { value: "medium", label: m.severity_medium },
        { value: "low", label: m.severity_low },
      ],
    },
    {
      key: "status",
      label: m.filter_facet_status,
      values: [
        { value: "open", label: m.status_open },
        { value: "in_pr", label: m.status_in_pr },
        { value: "in_progress", label: m.status_in_progress },
        { value: "resolved", label: m.status_resolved },
        { value: "dismissed", label: m.status_dismissed },
      ],
    },
  ];

  function selected(key: FacetKey): string[] {
    return (filter[key] as string[] | undefined) ?? [];
  }

  function emit(key: FacetKey, next: string[]) {
    onfilter({ ...filter, [key]: next.length ? next : undefined } as DebtFilter);
  }

  function toggle(key: FacetKey, value: string) {
    const cur = selected(key);
    emit(key, cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value]);
  }

  function labelOf(facet: Facet, value: string): string {
    return facet.values.find((v) => v.value === value)?.label() ?? value;
  }

  // 現在の選択をピル（scope:value）に展開
  const pills = $derived(
    FACETS.flatMap((f) =>
      selected(f.key).map((v) => ({ facet: f, value: v, text: `${f.label()}: ${labelOf(f, v)}` })),
    ),
  );

  const hasFilter = $derived(pills.length > 0);

  function recentSummary(f: DebtFilter): string {
    return FACETS.flatMap((facet) =>
      ((f[facet.key] as string[] | undefined) ?? []).map((v) => labelOf(facet, v)),
    ).join(" · ");
  }
</script>

<div class="flex flex-wrap items-center gap-2 rounded-md border bg-card p-2">
  <!-- ファセットごとの多選択ドロップダウン -->
  {#each FACETS as facet (facet.key)}
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        {#snippet child({ props })}
          <Button {...props} variant="outline" size="sm" class="gap-1">
            {facet.label()}
            {#if selected(facet.key).length}
              <span class="text-muted-foreground">({selected(facet.key).length})</span>
            {/if}
            <ChevronDown class="size-3.5" />
          </Button>
        {/snippet}
      </DropdownMenu.Trigger>
      <DropdownMenu.Content class="w-48">
        {#each facet.values as v (v.value)}
          <DropdownMenu.CheckboxItem
            checked={selected(facet.key).includes(v.value)}
            closeOnSelect={false}
            onCheckedChange={() => toggle(facet.key, v.value)}
          >
            {v.label()}
          </DropdownMenu.CheckboxItem>
        {/each}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  {/each}

  <!-- 最近の検索 -->
  <DropdownMenu.Root>
    <DropdownMenu.Trigger>
      {#snippet child({ props })}
        <Button {...props} variant="ghost" size="sm" class="gap-1 text-muted-foreground">
          <History class="size-3.5" />
          {m.filter_recent()}
        </Button>
      {/snippet}
    </DropdownMenu.Trigger>
    <DropdownMenu.Content class="w-64">
      {#if recentSearches.searches.length === 0}
        <DropdownMenu.Label class="text-xs font-normal text-muted-foreground"
          >{m.filter_recent_empty()}</DropdownMenu.Label
        >
      {:else}
        {#each recentSearches.searches as s, i (i)}
          <DropdownMenu.Item onSelect={() => onfilter(s)}>
            <span class="truncate text-xs">{recentSummary(s)}</span>
          </DropdownMenu.Item>
        {/each}
      {/if}
    </DropdownMenu.Content>
  </DropdownMenu.Root>

  <!-- 選択中トークンのピル -->
  {#if hasFilter}
    <div class="flex flex-1 flex-wrap items-center gap-1">
      {#each pills as p (p.facet.key + p.value)}
        <Badge variant="secondary" class="gap-1">
          {p.text}
          <button
            type="button"
            onclick={() => toggle(p.facet.key, p.value)}
            aria-label={`${p.text} を外す`}
            class="rounded-full hover:text-foreground"
          >
            <X class="size-3" />
          </button>
        </Badge>
      {/each}
      <button
        type="button"
        onclick={() => onfilter({})}
        class="ml-1 text-xs text-muted-foreground hover:text-foreground"
      >
        {m.filter_clear()}
      </button>
    </div>
  {/if}
</div>
