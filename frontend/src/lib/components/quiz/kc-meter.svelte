<script lang="ts">
  import { untrack } from "svelte";
  import { Tween } from "svelte/motion";
  import { cubicOut } from "svelte/easing";

  // KC を before → after へ補間し、会計帳簿が繰り上がる Re:Pay の演出を出す。
  type Props = { before: number; after: number };
  const { before, after }: Props = $props();

  // 初期値は before を一度だけキャプチャ（以降は after へ補間）。
  const pct = new Tween(untrack(() => before) * 100, { duration: 1200, easing: cubicOut });
  $effect(() => {
    pct.target = after * 100;
  });
</script>

<div class="flex items-center gap-3">
  <span class="font-display text-2xl font-semibold tabular-nums">{Math.round(pct.current)}%</span>
  <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
    <div class="h-full rounded-full bg-debt-knowledge" style="width: {pct.current}%"></div>
  </div>
  <span class="text-sm font-medium text-success">+{Math.round((after - before) * 100)}pt</span>
</div>
