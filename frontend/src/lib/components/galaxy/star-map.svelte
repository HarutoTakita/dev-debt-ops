<script lang="ts">
  import ZoomIn from "@lucide/svelte/icons/zoom-in";
  import ZoomOut from "@lucide/svelte/icons/zoom-out";
  import Maximize from "@lucide/svelte/icons/maximize";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import GraphCanvas from "./graph-canvas.svelte";
  import { toFileFunctionGraphData, toFileGraphData, type GraphNode } from "./graph-data";
  import { getFileFunctionGraph } from "$lib/api/client";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 理解度マップ（issue 288）。既定は「ファイル単位グラフ」（プロジェクト全体・KC 着色）。機能フィルタで
  // その機能に属するファイルのみに絞り込める。ファイルをクリックすると「そのファイル内の関数コールグラフ
  // （Level 3）」へドリル。描画は force-graph(canvas) ラッパ GraphCanvas に委譲（力学配置/衝突回避/ズーム）。
  // fileEdges: CodeGraphContext 由来の file↔file 結合（空なら galaxy.wormholes=import グラフにフォールバック）。
  const {
    galaxy,
    orgSlug = "",
    projectSlug = "",
    fileEdges = [],
  }: {
    galaxy: PersonalGalaxy;
    orgSlug?: string;
    projectSlug?: string;
    fileEdges?: { source: string; target: string }[];
  } = $props();

  let activeFeature = $state<string | null>(null); // フィルタ（null = 全ファイル）
  let selectedFile = $state<string | null>(null); // 非 null = Level 3（ファイル内関数グラフ）
  let controls = $state<{ zoomIn: () => void; zoomOut: () => void; fit: () => void }>();

  // --- Level 3: ファイル内の関数コールグラフ（ファイルクリック時に遅延取得） ---
  let fnNodes = $state<string[]>([]);
  let fnEdges = $state<{ source: string; target: string }[]>([]);
  let fnLoading = $state(false);
  async function openFile(path: string) {
    if (!orgSlug || !projectSlug) return; // デモ/未接続では開かない
    selectedFile = path;
    fnLoading = true;
    fnNodes = [];
    fnEdges = [];
    try {
      const g = await getFileFunctionGraph(orgSlug, projectSlug, path);
      if (selectedFile !== path) return; // レース
      fnNodes = g.nodes.map((n) => n.id);
      fnEdges = g.edges;
    } catch {
      /* 取得失敗 → 空表示（graceful） */
    } finally {
      if (selectedFile === path) fnLoading = false;
    }
  }

  // ファイル一覧（全 system のファイル）と、ファイル間エッジ（fileEdges 優先・無ければ wormhole=import）。
  const files = $derived(galaxy.systems.flatMap((s) => s.files));
  const edges = $derived(
    fileEdges.length > 0 ? fileEdges : galaxy.wormholes.map((w) => ({ source: w.from, target: w.to })),
  );

  const graphData = $derived.by(() => {
    if (selectedFile !== null) return toFileFunctionGraphData(fnNodes, fnEdges);
    return toFileGraphData(files, edges, activeFeature);
  });

  function handleNodeClick(node: GraphNode) {
    if (selectedFile !== null) return; // L3: ドリルなし
    if (node.kind === "file") openFile(node.file ?? node.id); // ファイル → 関数グラフ
  }

  const backClass =
    "mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground";
  const zoomBtnClass =
    "rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground";
  function chipClass(active: boolean): string {
    return cn(
      "rounded-full border px-2.5 py-0.5 text-xs transition",
      active
        ? "border-debt-knowledge bg-debt-knowledge/15 text-foreground"
        : "border-border bg-background text-muted-foreground hover:text-foreground",
    );
  }
</script>

{#if selectedFile !== null}
  <!-- Level 3 → ファイル単位グラフに戻る（フィルタは維持）。 -->
  <button type="button" onclick={() => (selectedFile = null)} class={backClass}>
    ← <span class="font-mono">{selectedFile}</span>
  </button>
{:else if galaxy.features.length > 0}
  <!-- 機能フィルタ（≤5 個）。全て / 各機能でファイルを絞り込む。 -->
  <div class="mb-2 flex flex-wrap items-center gap-1.5">
    <span class="text-xs text-muted-foreground">{m.galaxy_filter_label()}:</span>
    <button type="button" class={chipClass(activeFeature === null)} onclick={() => (activeFeature = null)}>
      {m.galaxy_filter_all()}
    </button>
    {#each galaxy.features as f (f.key)}
      <button
        type="button"
        class={chipClass(activeFeature === f.key)}
        onclick={() => (activeFeature = activeFeature === f.key ? null : f.key)}
      >
        {f.name}
      </button>
    {/each}
  </div>
{/if}

<div class="relative h-full min-h-[24rem] overflow-hidden rounded-lg border bg-card">
  {#if files.length === 0}
    <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
      <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_features()}</p>
    </div>
  {:else}
    <GraphCanvas
      nodes={graphData.nodes}
      links={graphData.links}
      onNodeClick={handleNodeClick}
      bindControls={(c) => (controls = c)}
    />

    <!-- 遅延取得中 / 空のオーバーレイ（canvas の上に重ねる） -->
    {#if selectedFile !== null && fnLoading}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
        <span class="text-xs text-muted-foreground">{m.common_loading()}</span>
      </div>
    {:else if selectedFile !== null && fnNodes.length === 0}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6 text-center">
        <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_functions()}</p>
      </div>
    {:else if selectedFile === null && graphData.nodes.length === 0}
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
