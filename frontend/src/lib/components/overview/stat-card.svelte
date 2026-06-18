<script lang="ts">
  import type { Snippet } from "svelte";

  // GitLab GlSingleStat の写像: 大きな数値 + ラベル + 任意のトレンド。
  type Props = { label: string; value: string; trend?: Snippet };
  const { label, value, trend }: Props = $props();
</script>

<div class="rounded-lg border bg-card p-4">
  <div class="text-xs text-muted-foreground">{label}</div>
  <div class="mt-1 flex items-baseline gap-2">
    <span class="font-display text-2xl font-semibold tabular-nums">{value}</span>
    {#if trend}{@render trend()}{/if}
  </div>
</div>
