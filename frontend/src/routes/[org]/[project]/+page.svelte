<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { overviewMock } from "$lib/mock/overview-mock";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { Button } from "$lib/components/ui/button";
  import ComingSoonPlaceholder from "$lib/components/overview/coming-soon-placeholder.svelte";
  import OverviewDashboard from "$lib/components/overview/overview-dashboard.svelte";
  import GettingStarted from "$lib/components/overview/getting-started.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  // 負債スコア・KC を算出する集計バックエンドは未実装（仕様書 §10.3 で後続フェーズ）。
  // 現状の overviewMock はモックデータのため、接続直後にいきなり実データのように見せない。
  // 接続直後はスキャン進行中の中間状態を出し、一定時間後（または CTA）で結果を表示する。
  $effect(() => {
    if (repo.connected && repo.scanState === "scanning") {
      const timer = setTimeout(() => repo.finishScan(), 2000);
      return () => clearTimeout(timer);
    }
  });
</script>

<svelte:head>
  <title>{m.nav_overview()} · Rosetta</title>
</svelte:head>

{#if !repo.connected}
  <ComingSoonPlaceholder ctaHref={resolve(`/${orgSlug}/${projectSlug}/repos`)}>
    {#snippet preview()}
      <OverviewDashboard overview={overviewMock} />
    {/snippet}
  </ComingSoonPlaceholder>
{:else if repo.scanState === "scanning"}
  <!-- スキャン進行中: ぼかしプレビュー + 不確定バー + CTA。偽データを完成結果として見せない。 -->
  <div class="relative h-full overflow-hidden">
    <div class="pointer-events-none absolute inset-0 overflow-hidden opacity-40 blur-[1px]" aria-hidden="true">
      <OverviewDashboard overview={overviewMock} />
    </div>
    <div class="absolute inset-0 flex items-center justify-center bg-background/60 p-4">
      <div class="w-full max-w-md space-y-4 rounded-lg border bg-card p-6 text-center shadow-sm">
        <h2 class="font-display text-lg font-semibold">{m.overview_scan_title()}</h2>
        <p class="text-sm leading-relaxed text-muted-foreground">{m.overview_scan_desc()}</p>
        <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div class="indeterminate-bar h-full w-1/3 rounded-full bg-debt-knowledge"></div>
        </div>
        <Button onclick={() => repo.finishScan()}>{m.overview_scan_cta()}</Button>
      </div>
    </div>
  </div>
{:else}
  <div class="mx-auto max-w-5xl px-4 pt-4">
    <GettingStarted />
  </div>
  <OverviewDashboard overview={overviewMock} isSample />
{/if}

<style>
  /* 不確定（indeterminate）プログレスバー。reduced-motion は後続 issue 024 でグローバル対応。 */
  @keyframes indeterminate {
    0% {
      transform: translateX(-120%);
    }
    100% {
      transform: translateX(360%);
    }
  }
  .indeterminate-bar {
    animation: indeterminate 1.2s ease-in-out infinite;
  }
</style>
