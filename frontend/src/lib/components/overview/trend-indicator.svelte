<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import { cn } from "$lib/utils";

  // GitLab trend_indicator.vue の写像。trendStyle で色の意味を切り替える。
  // asc: 増加 = success（緑）/ desc（負債系）: 減少 = success に反転（GitLab TREND_STYLE_DESC 相当）。
  // change === 0（変化なし・履歴なし）は矢印を出さず「±0」を muted で表示（KcMeter の ±0% と同じ流儀）。
  type Props = { change: number; trendStyle?: "asc" | "desc"; suffix?: string };
  const { change, trendStyle = "asc", suffix = "" }: Props = $props();

  const up = $derived(change > 0);
  const down = $derived(change < 0);
  const positive = $derived(trendStyle === "desc" ? down : up);
  const colorClass = $derived(change === 0 ? "text-muted-foreground" : positive ? "text-success" : "text-destructive");
</script>

<span class={cn("inline-flex items-center gap-0.5 text-xs font-medium tabular-nums", colorClass)}>
  {#if up}<ArrowUp class="size-3" />{:else if down}<ArrowDown class="size-3" />{/if}
  {change === 0 ? "±" : ""}{Math.abs(change)}{suffix}
</span>
