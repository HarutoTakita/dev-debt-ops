<script lang="ts">
  import ZoomIn from "@lucide/svelte/icons/zoom-in";
  import ZoomOut from "@lucide/svelte/icons/zoom-out";
  import Maximize from "@lucide/svelte/icons/maximize";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import GraphCanvas from "./graph-canvas.svelte";
  import { toFileGraphData } from "./graph-data";
  import * as m from "$lib/paraglide/messages";

  // 理解度マップ（issue 288/290/293）: プロジェクト全体の「ファイル単位グラフ」。ノード=ファイル（KC で色分け）、
  // エッジ=ファイル間の呼び出し/依存。機能フィルタ（`activeFeature`）は親（+page）が保持しマップ／リスト共用。
  // 指定時は「その機能のファイル＋グラフ隣接（1 ホップ）」に広げ、関連コードを含む連結クラスタを表示する
  // （toFileGraphData 参照）。孤立ノードも同関数内で最寄りへ接続。描画は force-graph(canvas) ラッパへ委譲。
  // fileEdges: CodeGraphContext 由来の file↔file 結合。import 由来の wormhole と併せて連結性を上げる。
  const {
    galaxy,
    fileEdges = [],
    activeFeature = null,
  }: {
    galaxy: PersonalGalaxy;
    fileEdges?: { source: string; target: string }[];
    activeFeature?: string | null;
  } = $props();

  let controls = $state<{ zoomIn: () => void; zoomOut: () => void; fit: () => void }>();

  // ファイル一覧（全 system のファイル）と、ファイル間エッジ。連結性を上げるため CGC の file_edges と
  // import 由来 wormhole の「和」を使う（重複除去・孤立ノード接続・機能近傍展開は toFileGraphData 側）。
  const files = $derived(galaxy.systems.flatMap((s) => s.files));
  const edges = $derived([...fileEdges, ...galaxy.wormholes.map((w) => ({ source: w.from, target: w.to }))]);
  const graphData = $derived(toFileGraphData(files, edges, activeFeature));

  const zoomBtnClass =
    "rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground";
</script>

<div class="flex h-full flex-col gap-2">
  <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg border bg-card">
    {#if files.length === 0}
      <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
        <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_features()}</p>
      </div>
    {:else}
      <GraphCanvas nodes={graphData.nodes} links={graphData.links} bindControls={(c) => (controls = c)} />

      {#if graphData.nodes.length === 0}
        <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6 text-center">
          <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_files()}</p>
        </div>
      {/if}

      <!-- ズーム操作 -->
      <div class="absolute right-2 bottom-2 z-10 flex flex-col gap-1">
        <button
          type="button"
          onclick={() => controls?.zoomIn()}
          aria-label={m.galaxy_zoom_in()}
          title={m.galaxy_zoom_in()}
          class={zoomBtnClass}
        >
          <ZoomIn class="size-4" />
        </button>
        <button
          type="button"
          onclick={() => controls?.zoomOut()}
          aria-label={m.galaxy_zoom_out()}
          title={m.galaxy_zoom_out()}
          class={zoomBtnClass}
        >
          <ZoomOut class="size-4" />
        </button>
        <button
          type="button"
          onclick={() => controls?.fit()}
          aria-label={m.galaxy_zoom_reset()}
          title={m.galaxy_zoom_reset()}
          class={zoomBtnClass}
        >
          <Maximize class="size-4" />
        </button>
      </div>
    {/if}
  </div>
</div>
