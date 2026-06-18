<script lang="ts">
  import ArrowUpDown from "@lucide/svelte/icons/arrow-up-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import type { DebtSort } from "$lib/api/client";
  import { Button } from "$lib/components/ui/button";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as m from "$lib/paraglide/messages";

  // ソートキー（深刻度 / 検出日 / 推定返済コスト）+ 昇降順トグル。
  type Props = { sort: DebtSort; onsort: (s: DebtSort) => void };
  const { sort, onsort }: Props = $props();

  const KEYS: { key: DebtSort["key"]; label: () => string }[] = [
    { key: "severity", label: m.sort_severity },
    { key: "detected_at", label: m.sort_detected_at },
    { key: "estimated_repay_hours", label: m.sort_cost },
  ];

  const currentLabel = $derived(KEYS.find((k) => k.key === sort.key)?.label() ?? "");

  function setKey(key: DebtSort["key"]) {
    onsort({ ...sort, key });
  }
  function toggleDir() {
    onsort({ ...sort, dir: sort.dir === "asc" ? "desc" : "asc" });
  }
</script>

<div class="flex items-center gap-1">
  <span class="text-xs text-muted-foreground">{m.sort_label()}</span>
  <DropdownMenu.Root>
    <DropdownMenu.Trigger>
      {#snippet child({ props })}
        <Button {...props} variant="outline" size="sm" class="gap-1">
          <ArrowUpDown class="size-3.5" />
          {currentLabel}
          <ChevronDown class="size-3.5" />
        </Button>
      {/snippet}
    </DropdownMenu.Trigger>
    <DropdownMenu.Content class="w-40" align="end">
      {#each KEYS as k (k.key)}
        <DropdownMenu.CheckboxItem checked={sort.key === k.key} onCheckedChange={() => setKey(k.key)}>
          {k.label()}
        </DropdownMenu.CheckboxItem>
      {/each}
    </DropdownMenu.Content>
  </DropdownMenu.Root>
  <Button
    variant="outline"
    size="icon-sm"
    onclick={toggleDir}
    aria-label={sort.dir === "asc" ? m.sort_dir_asc() : m.sort_dir_desc()}
    title={sort.dir === "asc" ? m.sort_dir_asc() : m.sort_dir_desc()}
  >
    {#if sort.dir === "asc"}<ArrowUp class="size-3.5" />{:else}<ArrowDown class="size-3.5" />{/if}
  </Button>
</div>
