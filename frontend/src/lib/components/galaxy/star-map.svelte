<script lang="ts">
  import ZoomIn from "@lucide/svelte/icons/zoom-in";
  import ZoomOut from "@lucide/svelte/icons/zoom-out";
  import Maximize from "@lucide/svelte/icons/maximize";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import GraphCanvas from "./graph-canvas.svelte";
  import { fileMasteryByPath } from "./galaxy-graph";
  import {
    toFeatureFunctionGraphData,
    toFeatureGraphData,
    toFileFunctionGraphData,
    type GraphNode,
  } from "./graph-data";
  import { getFeatureFunctionGraph, getFileFunctionGraph } from "$lib/api/client";
  import { formatKc } from "$lib/format/kc";
  import * as m from "$lib/paraglide/messages";

  // 3 段の理解度マップ。L1=機能ノード, L2=機能の関数レベルグラフ（file-hub + 関数）, L3=単一ファイルの関数
  // コールグラフ。描画は force-graph(canvas) ラッパ GraphCanvas に委譲（力学配置/衝突回避/ズーム/パン/
  // ドラッグ, issue 284）。orgSlug/projectSlug は L2/L3 の遅延取得に使う（未指定=デモでは取得しない）。
  const {
    galaxy,
    orgSlug = "",
    projectSlug = "",
  }: { galaxy: PersonalGalaxy; orgSlug?: string; projectSlug?: string } = $props();

  let selected = $state<string | null>(null); // 選択中の feature key（null = L1）
  let selectedFile = $state<string | null>(null); // 選択中のファイル（非 null = L3）
  let controls = $state<{ zoomIn: () => void; zoomOut: () => void; fit: () => void }>();

  // --- L3: ファイル内の関数コールグラフ（file-hub クリック時に遅延取得） ---
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

  // --- L2: 機能の関数レベルグラフ（機能クリック時に遅延取得） ---
  let featNodes = $state<{ id: string; label: string; file: string; kind: "file" | "function" }[]>([]);
  let featEdges = $state<{ source: string; target: string; type: "contains" | "calls" }[]>([]);
  let featLoading = $state(false);
  let featTruncated = $state(false);
  async function openFeature(key: string) {
    selected = key;
    selectedFile = null;
    if (!orgSlug || !projectSlug) {
      featNodes = [];
      featEdges = [];
      return; // デモ/未接続では取得しない
    }
    featLoading = true;
    featNodes = [];
    featEdges = [];
    featTruncated = false;
    try {
      const g = await getFeatureFunctionGraph(orgSlug, projectSlug, key);
      if (selected !== key) return; // レース
      featNodes = g.nodes;
      featEdges = g.edges;
      featTruncated = g.truncated;
    } catch {
      /* 取得失敗 → 空表示（graceful） */
    } finally {
      if (selected === key) featLoading = false;
    }
  }

  const selectedFeature = $derived(galaxy.features.find((f) => f.key === selected) ?? null);
  // データ更新で選択中の機能が消えたら L1 に戻す。
  $effect(() => {
    if (selected !== null && !galaxy.features.some((f) => f.key === selected)) {
      selected = null;
      selectedFile = null;
    }
  });

  const fileMap = $derived(fileMasteryByPath(galaxy)); // path → FileMastery（file-hub の KC 着色）
  const graphData = $derived.by(() => {
    if (selectedFile !== null) return toFileFunctionGraphData(fnNodes, fnEdges);
    if (selected !== null) return toFeatureFunctionGraphData(featNodes, featEdges, fileMap);
    return toFeatureGraphData(galaxy.features, galaxy.feature_edges);
  });

  function handleNodeClick(node: GraphNode) {
    if (selectedFile !== null) return; // L3: ドリルなし
    if (selected !== null) {
      if (node.kind === "file" && node.file) openFile(node.file); // L2: file-hub → L3
      return;
    }
    if (node.kind === "feature") openFeature(node.id); // L1: 機能 → L2
  }

  const backClass =
    "mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground";
  const zoomBtnClass =
    "rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground";
</script>

<!-- 戻るナビ（1 段ずつ戻る） -->
{#if selectedFile !== null}
  <button type="button" onclick={() => (selectedFile = null)} class={backClass}>
    ← <span class="font-mono">{selectedFile}</span>
  </button>
{:else if selected !== null && selectedFeature}
  <button type="button" onclick={() => (selected = null)} class={backClass}>
    ← {selectedFeature.name} · {formatKc(selectedFeature.kc)}
  </button>
{/if}

<div class="relative h-full min-h-[24rem] overflow-hidden rounded-lg border bg-card">
  {#if galaxy.features.length === 0}
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

    <!-- 遅延取得中 / 空 / 打ち切りのオーバーレイ（canvas の上に重ねる） -->
    {#if (selectedFile !== null && fnLoading) || (selected !== null && selectedFile === null && featLoading)}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
        <span class="text-xs text-muted-foreground">{m.common_loading()}</span>
      </div>
    {:else if (selectedFile !== null && fnNodes.length === 0) || (selected !== null && selectedFile === null && featNodes.length === 0)}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6 text-center">
        <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_functions()}</p>
      </div>
    {/if}

    {#if selected !== null && selectedFile === null && featTruncated}
      <div
        class="pointer-events-none absolute bottom-2 left-2 rounded bg-muted/80 px-2 py-1 text-[10px] text-muted-foreground"
      >
        {m.galaxy_graph_truncated()}
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
