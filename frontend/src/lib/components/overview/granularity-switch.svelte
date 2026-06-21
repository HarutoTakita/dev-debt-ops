<script lang="ts">
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 粒度切替セグメント（issue 056）。feature/folder/file は選択可、class/function は将来枠（disabled）。
  export type Granularity = "feature" | "folder" | "file";
  type Props = { value: Granularity; onChange: (g: Granularity) => void };
  const { value, onChange }: Props = $props();

  const options: { key: Granularity; label: () => string }[] = [
    { key: "feature", label: m.granularity_feature },
    { key: "folder", label: m.granularity_folder },
    { key: "file", label: m.granularity_file },
  ];
  // class/function は issue 057 で実計測。今は将来枠として見せるが選択不可。
  const comingSoon: { label: () => string }[] = [{ label: m.granularity_class }, { label: m.granularity_function }];
</script>

<div class="inline-flex items-center gap-2">
  <span class="text-xs text-muted-foreground">{m.granularity_label()}</span>
  <div class="inline-flex rounded-md border p-0.5">
    {#each options as o (o.key)}
      <button
        type="button"
        onclick={() => onChange(o.key)}
        aria-pressed={value === o.key}
        class={cn(
          "rounded px-2.5 py-1 text-xs transition-colors",
          value === o.key ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/50",
        )}
      >
        {o.label()}
      </button>
    {/each}
    {#each comingSoon as o, i (i)}
      <button
        type="button"
        disabled
        title={m.granularity_coming_soon()}
        class="cursor-not-allowed rounded px-2.5 py-1 text-xs text-muted-foreground/40"
      >
        {o.label()}
      </button>
    {/each}
  </div>
</div>
