<script lang="ts">
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 機能フィルタのチップ列（マップ／リスト両ビュー共用, issue 293）。`active` を bind して親が保持し、
  // マップ・リストの双方に同じフィルタを適用する。features が無ければ何も出さない。
  let {
    features,
    active = $bindable(),
  }: {
    features: PersonalGalaxy["features"];
    active: string | null;
  } = $props();

  function chipClass(isActive: boolean): string {
    return cn(
      "rounded-full border px-2.5 py-0.5 text-xs transition",
      isActive
        ? "border-debt-knowledge bg-debt-knowledge/15 text-foreground"
        : "border-border bg-background text-muted-foreground hover:text-foreground",
    );
  }
</script>

{#if features.length > 0}
  <div class="flex flex-wrap items-center gap-1.5" data-tour="galaxy-filter">
    <span class="text-xs text-muted-foreground">{m.galaxy_filter_label()}:</span>
    <button type="button" class={chipClass(active === null)} onclick={() => (active = null)}>
      {m.galaxy_filter_all()}
    </button>
    {#each features as f (f.key)}
      <button
        type="button"
        class={chipClass(active === f.key)}
        onclick={() => (active = active === f.key ? null : f.key)}
      >
        {f.name}
      </button>
    {/each}
  </div>
{/if}
