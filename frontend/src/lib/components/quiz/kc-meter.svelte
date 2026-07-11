<script lang="ts">
  import { untrack } from "svelte";
  import { Tween } from "svelte/motion";
  import { cubicOut } from "svelte/easing";
  import { formatKcPct } from "$lib/format/kc";
  import { cn } from "$lib/utils";

  // KC を before → after へ補間し、会計帳簿が繰り上がる Re:Pay の演出を出す。
  // showDelta: 再受験（2回目以降）のときだけ前回比の差分を表示する。初回は前回値が無く、差分が
  // 「クイズ結果 vs 著作推定」で紛らわしいため出さない。
  type Props = { before: number; after: number; showDelta?: boolean };
  const { before, after, showDelta = false }: Props = $props();

  // 差分は % 表示（旧: pt）。符号つき・向きで色分け（増=success / 減=destructive / 変化なし=muted）。
  const deltaPct = $derived(Math.round((after - before) * 100));

  // reduced-motion 設定時は補間を即時化する（+Xpt の最終表示は維持する）。
  const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // 初期値は before を一度だけキャプチャ（以降は after へ補間）。
  const pct = new Tween(untrack(() => before) * 100, { duration: reduceMotion ? 0 : 1200, easing: cubicOut });
  $effect(() => {
    pct.target = after * 100;
  });
</script>

<div class="flex items-center gap-3">
  <span class="font-display text-2xl font-semibold tabular-nums">{formatKcPct(pct.current / 100)}</span>
  <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
    <div class="h-full rounded-full bg-debt-knowledge/60" style="width: {pct.current}%"></div>
  </div>
  {#if showDelta}
    <span
      class={cn(
        "text-sm font-medium tabular-nums",
        deltaPct > 0 ? "text-success" : deltaPct < 0 ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {deltaPct > 0 ? "+" : deltaPct < 0 ? "−" : "±"}{Math.abs(deltaPct)}%
    </span>
  {/if}
</div>
