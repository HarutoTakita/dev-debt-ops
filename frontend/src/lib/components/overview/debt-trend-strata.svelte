<script lang="ts">
  import type { DebtTrendPoint } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 推移を「地層断面」として描く。各週を 1 層として積み、最新週を最上層に置く。
  // ダッシュボードは正の向き（コード品質 × 理解度）で統一。アンバーのバー = コード品質（= 1 - コード負債
  // スコア。週を追うごとに伸びる）、トラック（ティール）= 理解度の土台。
  type Props = { trend: DebtTrendPoint[] };
  const { trend }: Props = $props();

  const layers = $derived([...trend].reverse()); // 今週（最新）を最上層へ
  const pct = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 100);
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
          <div class="absolute inset-y-0 left-0 bg-debt-code/55" style="width: {100 - pct(p.code_debt_score)}%"></div>
        </div>
        <span class="w-32 shrink-0 text-right text-muted-foreground tabular-nums">
          {m.overview_trend_legend_debt()}
          {100 - pct(p.code_debt_score)} / {m.overview_trend_legend_kc()}
          {pct(p.knowledge_coverage)}
        </span>
      </div>
    {/each}
  </div>
</div>
