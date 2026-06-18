<script lang="ts">
  type Props = { value: number; showLabel?: boolean };
  const { value, showLabel = true }: Props = $props();

  const pct = $derived(Math.round(value * 100));
</script>

<div class="flex items-center gap-1.5">
  {#if showLabel}<span class="text-xs text-muted-foreground tabular-nums">KC {value.toFixed(2)}</span>{/if}
  <span class="relative h-1.5 w-16 overflow-hidden rounded-full bg-muted" title={`KC ${pct}%`}>
    <span class="absolute inset-y-0 left-0 rounded-full bg-debt-knowledge" style="width: {pct}%"></span>
  </span>
</div>
