<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import type { Overview } from "$lib/api/schemas";
  import { overviewMock } from "$lib/mock/overview-mock";
  import { repo } from "$lib/stores/repo-store.svelte";
  import ComingSoonPlaceholder from "$lib/components/overview/coming-soon-placeholder.svelte";
  import OverviewDashboard from "$lib/components/overview/overview-dashboard.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // 負債スコア・KC を算出する集計バックエンドは未実装（仕様書 §10.3 で後続フェーズ）。
  // プロジェクト内ではリポジトリが常に束縛されるため観測台（overviewMock）を描画する。
  // 後続 issue で getOverview() を await し、その結果に置き換える。
  const overview = $derived<Overview | null>(repo.connected ? overviewMock : null);
</script>

<svelte:head>
  <title>{m.nav_overview()} · Rosetta</title>
</svelte:head>

{#if overview}
  <OverviewDashboard {overview} />
{:else}
  <ComingSoonPlaceholder ctaHref={resolve(`/${orgSlug}/${projectSlug}/repos`)}>
    {#snippet preview()}
      <OverviewDashboard overview={overviewMock} />
    {/snippet}
  </ComingSoonPlaceholder>
{/if}
