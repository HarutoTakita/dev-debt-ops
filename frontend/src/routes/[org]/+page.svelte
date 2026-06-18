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

  // 負債スコア・KC を算出する集計バックエンドは未実装（仕様書 §10.3 で後続フェーズ）。
  // デモ用の暫定挙動: リポジトリ接続済みなら overviewMock を実データ扱いで観測台を描画し、
  // 未接続なら Coming Soon（背後にモックを透かす）を表示する。
  // 後続 issue で getOverview() を await し、その結果（無ければ未接続扱い）に置き換える。
  const overview = $derived<Overview | null>(repo.connected ? overviewMock : null);
</script>

<svelte:head>
  <title>{m.nav_overview()} · Rosetta</title>
</svelte:head>

{#if overview}
  <OverviewDashboard {overview} />
{:else}
  <ComingSoonPlaceholder ctaHref={resolve(`/${orgSlug}/repos`)}>
    {#snippet preview()}
      <OverviewDashboard overview={overviewMock} />
    {/snippet}
  </ComingSoonPlaceholder>
{/if}
