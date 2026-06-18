<script lang="ts">
  import type { Overview } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import DebtMatrix from "./debt-matrix.svelte";
  import QuadrantLegend from "./quadrant-legend.svelte";
  import DebtTrendStrata from "./debt-trend-strata.svelte";
  import StatCard from "./stat-card.svelte";
  import TrendIndicator from "./trend-indicator.svelte";
  import WeeklyActivity from "./weekly-activity.svelte";
  import PriorityList from "./priority-list.svelte";

  // 観測台ダッシュボードの組み立て。preview（Coming Soon の透かし）と将来の実データ表示で共用する。
  type Props = { overview: Overview };
  const { overview }: Props = $props();

  const dangerCount = $derived(
    overview.files.filter((f) => f.code_debt_score > 0.5 && f.knowledge_coverage < 0.5).length,
  );
  const firstKc = $derived(Math.round((overview.trend.at(0)?.knowledge_coverage ?? 0) * 100));
  const latestKc = $derived(Math.round((overview.trend.at(-1)?.knowledge_coverage ?? 0) * 100));
  const kcChange = $derived(latestKc - firstKc);
</script>

<div class="mx-auto flex max-w-5xl flex-col gap-4 p-4">
  <!-- 一次ビュー: 二軸負債マトリクス + 4 象限凡例 -->
  <div class="grid gap-4 lg:grid-cols-[2fr_1fr]">
    <DebtMatrix files={overview.files} />
    <QuadrantLegend />
  </div>

  <!-- stat-card（負債系は減少=緑に反転） -->
  <div class="grid gap-3 sm:grid-cols-3">
    <StatCard label={m.overview_stat_kc()} value={`${latestKc}%`}>
      {#snippet trend()}
        <TrendIndicator change={kcChange} trendStyle="asc" suffix="pt" />
      {/snippet}
    </StatCard>
    <StatCard label={m.overview_stat_danger()} value={`${dangerCount}`}>
      {#snippet trend()}
        <TrendIndicator change={-4} trendStyle="desc" suffix="件" />
      {/snippet}
    </StatCard>
    <StatCard label={m.overview_stat_repaid()} value={`${overview.activity.code_agent_merged}`}>
      {#snippet trend()}
        <TrendIndicator change={3} trendStyle="asc" suffix="件" />
      {/snippet}
    </StatCard>
  </div>

  <!-- 推移地層グラフ -->
  <div class="rounded-lg border bg-card p-4">
    <DebtTrendStrata trend={overview.trend} />
  </div>

  <!-- 二次ビュー: 今週の活動 + 優先対応リスト -->
  <div class="grid gap-4 sm:grid-cols-2">
    <div class="rounded-lg border bg-card p-4"><WeeklyActivity activity={overview.activity} /></div>
    <div class="rounded-lg border bg-card p-4"><PriorityList files={overview.files} /></div>
  </div>
</div>
