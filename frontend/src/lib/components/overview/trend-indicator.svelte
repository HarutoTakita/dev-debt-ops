<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import { cn } from "$lib/utils";

  // GitLab trend_indicator.vue の写像。trendStyle で色の意味を切り替える。
  // asc: 増加 = success（緑）/ desc（負債系）: 減少 = success に反転（GitLab TREND_STYLE_DESC 相当）。
  type Props = { change: number; trendStyle?: "asc" | "desc"; suffix?: string };
  const { change, trendStyle = "asc", suffix = "" }: Props = $props();

  const up = $derived(change > 0);
  const positive = $derived(trendStyle === "desc" ? !up : up);
  const colorClass = $derived(positive ? "text-success" : "text-destructive");
</script>

<span class={cn("inline-flex items-center gap-0.5 text-xs font-medium tabular-nums", colorClass)}>
  {#if up}<ArrowUp class="size-3" />{:else}<ArrowDown class="size-3" />{/if}
  {Math.abs(change)}{suffix}
</span>
