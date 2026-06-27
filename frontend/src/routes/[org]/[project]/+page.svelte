<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { overviewMock } from "$lib/mock/overview-mock";
  import { getOverview } from "$lib/api/client";
  import type { Overview } from "$lib/api/schemas";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { Button } from "$lib/components/ui/button";
  import ComingSoonPlaceholder from "$lib/components/overview/coming-soon-placeholder.svelte";
  import OverviewDashboard from "$lib/components/overview/overview-dashboard.svelte";
  import { type Granularity } from "$lib/components/overview/granularity-switch.svelte";
  import { ALL_STAGE_IDS } from "$lib/stores/analysis-run-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // 接続済みなら実データ（issue 031 の集計 API）を取得。
  // 取得失敗（エラー）と「データ無し（空）」を区別する: 空はサンプル表示、失敗は
  // 再試行 UI を出す（mock を実データ風に見せない、issue-044）。
  let overview = $state<Overview | null>(null);
  let overviewError = $state(false);
  // 粒度切替（issue 056）。変更すると getOverview を再取得する。
  let granularity = $state<Granularity>("file");
  async function loadOverview(g: Granularity = granularity) {
    if (!(repo.connected && orgSlug && projectSlug)) return;
    try {
      overview = await getOverview(orgSlug, projectSlug, g);
      overviewError = false;
    } catch {
      overview = null;
      overviewError = true;
    }
  }
  $effect(() => {
    const g = granularity; // 粒度変更で再取得（同期 read で依存に含める）
    if (repo.connected && orgSlug && projectSlug) {
      void loadOverview(g);
    }
  });

  // コックピットでいずれかのステージが完了したら観測台の集計を再取得（issue 049）。
  // loadOverview 内で接続/スキャン状態をガードしているため、未接続時は何もしない。
  refreshOnStageComplete(ALL_STAGE_IDS, () => void loadOverview());
</script>

<svelte:head>
  <title>{m.nav_overview()} · DevDebtOps</title>
</svelte:head>

{#if !repo.connected}
  <ComingSoonPlaceholder ctaHref={resolve(`/${orgSlug}/${projectSlug}/repos`)}>
    {#snippet preview()}
      <OverviewDashboard overview={overviewMock} />
    {/snippet}
  </ComingSoonPlaceholder>
{:else if overviewError}
  <div class="mx-auto max-w-5xl space-y-3 px-4 py-8 text-center">
    <p class="text-sm text-muted-foreground">{m.overview_load_error()}</p>
    <Button variant="outline" onclick={() => loadOverview()}>{m.common_retry()}</Button>
  </div>
{:else if overview && overview.files.length > 0}
  <OverviewDashboard {overview} {granularity} onGranularity={(g) => (granularity = g)} />
{:else}
  <OverviewDashboard overview={overviewMock} isSample />
{/if}
