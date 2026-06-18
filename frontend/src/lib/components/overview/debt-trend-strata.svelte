<script lang="ts">
  import type { DebtTrendPoint } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 推移を「地層断面」として描く。各週を 1 層として積み、最新週を最上層に置く。
  // トラック = 理解の堆積（ティール）、左から重なるアンバー = 残った負債。週を追うごとに負債層が薄くなる。
  type Props = { trend: DebtTrendPoint[] };
  const { trend }: Props = $props();

  const layers = $derived([...trend].reverse()); // 今週（最新）を最上層へ
</script>

<div>
  <div class="flex items-center justify-between">
    <span class="text-sm font-medium">{m.overview_trend_title()}</span>
    <div class="flex gap-3 text-[10px] text-muted-foreground">
      <span class="flex items-center gap-1">
        <span class="size-2 rounded-xs bg-debt-code/60"></span>{m.overview_trend_legend_debt()}
      </span>
      <span class="flex items-center gap-1">
        <span class="size-2 rounded-xs bg-debt-knowledge/40"></span>{m.overview_trend_legend_kc()}
      </span>
    </div>
  </div>

  <div class="mt-3 space-y-1">
    {#each layers as p (p.week)}
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 shrink-0 text-right text-muted-foreground">{p.week}</span>
        <div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-debt-knowledge/15">
          <div class="absolute inset-y-0 left-0 bg-debt-code/55" style="width: {p.code_debt_score * 100}%"></div>
        </div>
        <span class="w-28 shrink-0 text-right text-muted-foreground tabular-nums">
          負債 {Math.round(p.code_debt_score * 100)} / KC {Math.round(p.knowledge_coverage * 100)}
        </span>
      </div>
    {/each}
  </div>
</div>
