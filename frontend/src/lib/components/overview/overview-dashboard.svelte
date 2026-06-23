<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import type { ResolvedPathname } from "$app/types";
  import type { Overview } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";
  import DebtMatrix from "./debt-matrix.svelte";
  import QuadrantLegend from "./quadrant-legend.svelte";
  import DebtTrendStrata from "./debt-trend-strata.svelte";
  import StatCard from "./stat-card.svelte";
  import TrendIndicator from "./trend-indicator.svelte";
  import PriorityList from "./priority-list.svelte";
  import GranularitySwitch, { type Granularity } from "./granularity-switch.svelte";
  import FeatureDebtList from "./feature-debt-list.svelte";

  // 観測台ダッシュボードの組み立て。preview（Coming Soon の透かし）と将来の実データ表示で共用する。
  // isSample: 表示中のデータがモック由来である間「Sample / デモデータ」バッジを出す（誠実表示）。
  // granularity / onGranularity: 粒度切替（issue 056）。onGranularity 提供時のみセグメントを出す
  // （サンプル/モック表示では切替を出さない）。
  type Props = {
    overview: Overview;
    isSample?: boolean;
    granularity?: Granularity;
    onGranularity?: (g: Granularity) => void;
  };
  const { overview, isSample = false, granularity = "file", onGranularity }: Props = $props();

  // 遷移先生成用の slug。ルートからではなく $app/state 経由で取得（mastery-list / constructive-result と同流儀）。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const dangerHref = $derived(`${resolve(`/${orgSlug}/${projectSlug}/matrix`)}?cell=danger` as ResolvedPathname);
  const galaxyHref = $derived(resolve(`/${orgSlug}/${projectSlug}/galaxy`));

  const dangerCount = $derived(
    overview.files.filter((f) => f.code_debt_score > 0.5 && f.knowledge_coverage < 0.5).length,
  );
  const firstKc = $derived(Math.round((overview.trend.at(0)?.knowledge_coverage ?? 0) * 100));
  const latestKc = $derived(Math.round((overview.trend.at(-1)?.knowledge_coverage ?? 0) * 100));
  const kcChange = $derived(latestKc - firstKc);
</script>

<div class="mx-auto flex max-w-5xl flex-col gap-4 p-4">
  {#if isSample}
    <div class="flex items-center gap-2">
      <span class="rounded-full bg-warning/15 px-2.5 py-0.5 text-xs font-medium text-warning">
        {m.overview_sample_badge()}
      </span>
    </div>
  {/if}

  <!-- ヒーロー: 理解度（KC）を主役に、返済導線（Galaxy）を前面化（issue 059 リポジション） -->
  <div
    class="flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
    data-tour="overview-kc"
  >
    <div class="min-w-0">
      <div class="flex items-baseline gap-2">
        <span class="font-display text-3xl font-bold">{latestKc}%</span>
        <span class="text-sm font-medium text-muted-foreground">{m.overview_stat_kc()}</span>
      </div>
      <p class="mt-1 max-w-xl text-xs leading-relaxed text-muted-foreground">{m.overview_hero_desc()}</p>
    </div>
    <a
      href={galaxyHref}
      class="shrink-0 self-start rounded-md border px-3 py-1.5 text-sm font-medium text-primary hover:bg-accent/40 sm:self-auto"
    >
      {m.overview_hero_galaxy_cta()} →
    </a>
  </div>

  {#if onGranularity}
    <GranularitySwitch value={granularity} onChange={onGranularity} />
  {/if}

  <!-- 一次ビュー: granularity=file は二軸負債マトリクス、feature/folder は機能/フォルダ単位の理解負債リスト -->
  <div data-tour="overview-primary">
    {#if granularity === "file"}
      <div class="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <DebtMatrix {orgSlug} {projectSlug} files={overview.files} />
        <QuadrantLegend {orgSlug} {projectSlug} />
      </div>
    {:else}
      <FeatureDebtList {orgSlug} {projectSlug} features={overview.features} />
    {/if}
  </div>

  <!-- stat-card（負債系は減少=緑に反転） -->
  <div class="grid gap-3 sm:grid-cols-3" data-tour="overview-stats">
    <div class="relative">
      <StatCard label={m.overview_stat_kc()} value={`${latestKc}%`}>
        {#snippet trend()}
          <TrendIndicator change={kcChange} trendStyle="asc" suffix="pt" />
        {/snippet}
      </StatCard>
      <a href={galaxyHref} class="absolute top-3 right-3 text-xs font-medium text-primary hover:underline"
        >{m.overview_raise_kc()} →</a
      >
    </div>
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
  <div class="rounded-lg border bg-card p-4" data-tour="overview-trend">
    <DebtTrendStrata trend={overview.trend} />
  </div>

  <!-- 二次ビュー: 優先対応リスト -->
  <div class="rounded-lg border bg-card p-4" data-tour="overview-priority">
    <PriorityList {orgSlug} {projectSlug} files={overview.files} />
    {#if dangerCount > 0}
      <a href={dangerHref} class="mt-3 inline-block text-xs font-medium text-primary hover:underline"
        >{m.overview_view_all_danger({ count: dangerCount })} →</a
      >
    {/if}
  </div>
</div>
