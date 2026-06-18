<script lang="ts">
  import type { Branch } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { getLocale } from "$lib/paraglide/runtime";

  type Props = {
    branches: Branch[];
    selectedBranch: string;
    selectedPath: string | null;
    onbranchchange: (branch: string) => void;
    ondisconnect: () => void;
  };

  const { branches, selectedBranch, selectedPath, onbranchchange, ondisconnect }: Props = $props();

  type Crumb = { name: string; path: string };

  // GitLab breadcrumbs.vue の pathLinks（currentPath を累積パスへ reduce）を Svelte 5 runes で。
  const crumbs = $derived.by<Crumb[]>(() => {
    const c = repo.connected;
    if (!c) return [];
    const base: Crumb[] = [
      { name: c.owner, path: "" },
      { name: c.name, path: "" },
    ];
    if (!selectedPath) return base;
    const parts = selectedPath.split("/").filter(Boolean);
    return [...base, ...parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join("/") }))];
  });

  // last_commit.vue 風の最終更新（相対時刻）。CI パイプライン状態は持たないため、ドットは
  // 「データ取得済み」を示す軽い表現に留める。
  function relativeTime(iso: string): string {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const diff = then - Date.now();
    const rtf = new Intl.RelativeTimeFormat(getLocale(), { numeric: "auto" });
    const min = 60_000,
      hr = 60 * min,
      day = 24 * hr,
      mon = 30 * day,
      yr = 365 * day;
    const abs = Math.abs(diff);
    if (abs < hr) return rtf.format(Math.round(diff / min), "minute");
    if (abs < day) return rtf.format(Math.round(diff / hr), "hour");
    if (abs < mon) return rtf.format(Math.round(diff / day), "day");
    if (abs < yr) return rtf.format(Math.round(diff / mon), "month");
    return rtf.format(Math.round(diff / yr), "year");
  }

  function onChange(e: Event) {
    onbranchchange((e.target as HTMLSelectElement).value);
  }
</script>

{#if repo.connected}
  <header class="flex flex-col gap-1.5 border-b px-4 py-2">
    <div class="flex items-center gap-2">
      <nav class="flex min-w-0 flex-1 items-center gap-1 text-sm" aria-label="breadcrumb">
        {#each crumbs as crumb, i (i + crumb.name)}
          {#if i > 0}<span class="text-muted-foreground/60">/</span>{/if}
          <span
            class={cn("truncate", i === crumbs.length - 1 ? "font-medium text-foreground" : "text-muted-foreground")}
          >
            {crumb.name}
          </span>
        {/each}
      </nav>

      <select
        onchange={onChange}
        value={selectedBranch}
        class="rounded-md border px-2 py-1 text-sm"
        aria-label="ブランチ"
      >
        {#each branches as b (b.name)}
          <option value={b.name}>{b.name}{b.is_default ? " (default)" : ""}</option>
        {/each}
        {#if branches.length === 0}
          <option value={selectedBranch}>{selectedBranch}</option>
        {/if}
      </select>
      <button onclick={ondisconnect} class="text-sm text-muted-foreground hover:text-foreground">切断</button>
    </div>

    <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span class="size-1.5 rounded-full bg-success" aria-hidden="true"></span>
      <span>{relativeTime(repo.connected.updated_at)}に更新</span>
    </div>
  </header>
{/if}
