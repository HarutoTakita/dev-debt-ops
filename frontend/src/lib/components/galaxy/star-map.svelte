<script lang="ts">
  import ZoomIn from "@lucide/svelte/icons/zoom-in";
  import ZoomOut from "@lucide/svelte/icons/zoom-out";
  import Maximize from "@lucide/svelte/icons/maximize";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import { computeForceLayout, type Point } from "./force-layout";
  import { buildFeatureFunctionGraph, buildFeatureGraph, buildFunctionGraph, fileMasteryByPath } from "./galaxy-graph";
  import { getFeatureFunctionGraph, getFileFunctionGraph } from "$lib/api/client";
  import { formatKc } from "$lib/format/kc";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 3 段の理解度マップ。Level 1 = 機能（feature）ノード + 機能間グラフ。機能クリックで Level 2（その機能の
  // 関数レベルグラフ = ファイル=ハブ + 関数ノード, CONTAINS+CALLS, issue 282）へ。ファイルハブのクリックで
  // Level 3（そのファイル内の関数コールグラフ, issue 240）へ。「← 戻る」で 1 段ずつ戻る。
  // Map/Set の構築は galaxy-graph.ts / force-layout.ts（.ts 側）で完結させる（prefer-svelte-reactivity）。
  // orgSlug/projectSlug: Level-2/3 の遅延取得に使う（未指定＝デモでは遅延取得しない）。
  const {
    galaxy,
    orgSlug = "",
    projectSlug = "",
  }: {
    galaxy: PersonalGalaxy;
    orgSlug?: string;
    projectSlug?: string;
  } = $props();

  let selected = $state<string | null>(null); // 選択中の feature key（null = Level 1）
  let selectedFile = $state<string | null>(null); // 選択中のファイル（非 null = Level 3）
  let hovered = $state<string | null>(null);

  // --- Level 3: ファイル内の関数コールグラフ（issue 240、クリック時に遅延取得） ---
  let fnNodes = $state<string[]>([]);
  let fnEdges = $state<{ source: string; target: string }[]>([]);
  let fnLoading = $state(false);

  async function openFile(path: string) {
    if (!orgSlug || !projectSlug) return; // デモ/未接続では Level-3 を開かない
    selectedFile = path;
    hovered = null;
    fnLoading = true;
    fnNodes = [];
    fnEdges = [];
    try {
      const g = await getFileFunctionGraph(orgSlug, projectSlug, path);
      if (selectedFile !== path) return; // 別ファイルへ切替済み（レース）なら破棄
      fnNodes = g.nodes.map((n) => n.id);
      fnEdges = g.edges;
    } catch {
      /* 取得失敗 → 空表示（graceful） */
    } finally {
      if (selectedFile === path) fnLoading = false;
    }
  }

  const fnGraph = $derived(buildFunctionGraph(fnNodes, fnEdges));
  const fnLayout = $derived(
    computeForceLayout(
      fnNodes,
      fnEdges.map((e) => [e.source, e.target] as const),
    ),
  );
  const fnLines = $derived(
    fnGraph.edges.map(({ a, b }) => {
      const pa = fnLayout.get(a) ?? FALLBACK;
      const pb = fnLayout.get(b) ?? FALLBACK;
      return { a, b, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
    }),
  );

  const selectedFeature = $derived(galaxy.features.find((f) => f.key === selected) ?? null);
  // データ更新で選択中の機能が消えたら Level 1 に戻す（ファイル選択も解除）。
  $effect(() => {
    if (selected !== null && !galaxy.features.some((f) => f.key === selected)) {
      selected = null;
      selectedFile = null;
    }
  });

  const FALLBACK: Point = { x: 50, y: 50 };

  // --- Level 1: 機能グラフ ---
  const fgraph = $derived(buildFeatureGraph(galaxy.features, galaxy.feature_edges));
  const flayout = $derived(
    computeForceLayout(
      galaxy.features.map((f) => f.key),
      fgraph.edges.map((e) => [e.a, e.b] as const),
    ),
  );
  const fLines = $derived(
    fgraph.edges.map(({ a, b }) => {
      const pa = flayout.get(a) ?? FALLBACK;
      const pb = flayout.get(b) ?? FALLBACK;
      return { a, b, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
    }),
  );

  // --- Level 2: 機能の関数レベルグラフ（issue 282、機能クリック時に遅延取得） ---
  // ファイル=ハブノード + その関数=子ノード。CONTAINS（ハブ→関数）＋CALLS（関数→関数・ファイル跨ぎ含む）で
  // 接続し、全関数が必ずハブにつながる＝孤立ノードが出ない。ファイルハブは KC で着色（理解度レンズ維持）。
  let featNodes = $state<{ id: string; label: string; file: string; kind: "file" | "function" }[]>([]);
  let featEdges = $state<{ source: string; target: string; type: "contains" | "calls" }[]>([]);
  let featLoading = $state(false);
  let featTruncated = $state(false);

  async function openFeature(key: string) {
    selected = key;
    selectedFile = null;
    hovered = null;
    if (!orgSlug || !projectSlug) {
      featNodes = [];
      featEdges = [];
      return; // デモ/未接続では遅延取得しない
    }
    featLoading = true;
    featNodes = [];
    featEdges = [];
    featTruncated = false;
    try {
      const g = await getFeatureFunctionGraph(orgSlug, projectSlug, key);
      if (selected !== key) return; // 別機能へ切替済み（レース）なら破棄
      featNodes = g.nodes;
      featEdges = g.edges;
      featTruncated = g.truncated;
    } catch {
      /* 取得失敗 → 空表示（graceful） */
    } finally {
      if (selected === key) featLoading = false;
    }
  }

  const fileMap = $derived(fileMasteryByPath(galaxy)); // path → FileMastery（ハブの着色に使用）
  const featGraph = $derived(buildFeatureFunctionGraph(featNodes, featEdges));
  const featLayout = $derived(
    computeForceLayout(
      featNodes.map((n) => n.id),
      featEdges.map((e) => [e.source, e.target] as const),
    ),
  );
  const featLines = $derived(
    featGraph.edges.map(({ a, b }) => {
      const pa = featLayout.get(a) ?? FALLBACK;
      const pb = featLayout.get(b) ?? FALLBACK;
      return { a, b, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
    }),
  );

  // 関数ノードの淡い色相（ファイル単位でクラスタ色を分ける）。Map を作らない純関数。
  function fileHue(file: string): number {
    let h = 0;
    for (let i = 0; i < file.length; i++) h = (h * 31 + file.charCodeAt(i)) % 360;
    return h;
  }
  // ファイルハブの色（KC/mastery。Level-1 の featureClass と同じ理解度レンズ）。
  function hubClass(file: string): string {
    return featureClass(fileMap.get(file)?.mastery ?? "unexplored");
  }

  function edgeActive(l: { a: string; b: string }): boolean {
    return hovered !== null && (l.a === hovered || l.b === hovered);
  }
  function dimmed(neighbors: Map<string, Set<string>>, id: string): boolean {
    if (hovered === null || hovered === id) return false;
    return !(neighbors.get(hovered)?.has(id) ?? false);
  }
  // 機能ノードの色（理解ステータス。明るいキャンバスで読めるよう枠線 + 淡い背景で表す）。
  function featureClass(mastery: string): string {
    return (
      {
        star: "border-debt-knowledge bg-debt-knowledge/10 text-foreground",
        dim_star: "border-debt-knowledge/60 bg-debt-knowledge/5 text-foreground",
        black_hole: "border-destructive/70 bg-destructive/10 text-foreground",
        unexplored: "border-dashed border-border bg-muted text-muted-foreground",
      }[mastery] ?? "border-border bg-muted text-muted-foreground"
    );
  }

  // --- パン & ズーム（トラックパッド/マウスホイール + ドラッグ）。HTML ノード(%)と SVG(viewBox)を同じ
  // 正方形キャンバスに載せ、その親に transform をかけて両方を一括で拡大縮小・移動する。 ---
  let viewport = $state<HTMLDivElement | null>(null);
  let vw = $state(0);
  let vh = $state(0);
  const size = $derived(Math.min(vw, vh)); // キャンバス（正方形）の一辺 px。短辺に合わせる。
  let scale = $state(1);
  let tx = $state(0);
  let ty = $state(0);
  let dragging = $state(false);
  let lastX = 0;
  let lastY = 0;

  const MIN_SCALE = 0.4;
  const MAX_SCALE = 5;
  const clampScale = (s: number) => Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));

  function fit() {
    scale = 1;
    tx = (vw - size) / 2;
    ty = (vh - size) / 2;
  }
  // レベル切替（selected）や領域リサイズ（size）で全体表示にリセット。依存として明示的に読み（trigger）、
  // ユーザーのズーム値（scale/tx/ty）は読まないので、操作中に再実行して値を巻き戻すことはない。
  $effect(() => {
    const trigger = `${selected}:${selectedFile}:${size}`;
    if (trigger) fit();
  });

  function zoomAt(cx: number, cy: number, factor: number) {
    const ns = clampScale(scale * factor);
    const k = ns / scale;
    // 原点 (0,0) 基準の transform で、点 (cx,cy) の下のキャンバス座標を固定したままスケールする。
    tx = cx - (cx - tx) * k;
    ty = cy - (cy - ty) * k;
    scale = ns;
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault(); // ページスクロールを抑止し、ホイール/ピンチをズームに割り当てる。
    const rect = viewport?.getBoundingClientRect();
    if (!rect) return;
    zoomAt(e.clientX - rect.left, e.clientY - rect.top, Math.exp(-e.deltaY * 0.0015));
  }

  // ノード（クリックでドリル/ホバー）やズームボタンの上から始まったドラッグはパンにしない。
  function panIgnored(t: EventTarget | null): boolean {
    return t instanceof Element && t.closest("[data-node],[data-controls]") !== null;
  }
  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0 || panIgnored(e.target)) return;
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    viewport?.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e: PointerEvent) {
    if (!dragging) return;
    tx += e.clientX - lastX;
    ty += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
  }
  function onPointerUp(e: PointerEvent) {
    if (!dragging) return;
    dragging = false;
    viewport?.releasePointerCapture(e.pointerId);
  }
  // +/- ボタンは表示領域の中心を基準にズームする。
  const zoomButton = (factor: number) => zoomAt(vw / 2, vh / 2, factor);
</script>

{#if selectedFile !== null}
  <!-- Level 3 → Level 2 に戻る（クリックしたファイルのパスを表示）。 -->
  <button
    type="button"
    onclick={() => {
      selectedFile = null;
      hovered = null;
    }}
    class="mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
  >
    ← <span class="font-mono">{selectedFile}</span>
  </button>
{:else if selected !== null && selectedFeature}
  <button
    type="button"
    onclick={() => {
      selected = null;
      hovered = null;
    }}
    class="mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
  >
    ← {selectedFeature.name} · {formatKc(selectedFeature.kc)}
  </button>
{/if}

<!-- ズーム/パン可能なビューポート。内側の正方形キャンバスに transform をかけ、ノード(HTML %)と
     依存線(SVG viewBox)を共有座標系のまま一括で拡大縮小・移動する。 -->
<div
  bind:this={viewport}
  bind:clientWidth={vw}
  bind:clientHeight={vh}
  class="relative h-full min-h-[24rem] touch-none overflow-hidden rounded-lg border bg-card select-none"
  style="cursor: {dragging ? 'grabbing' : 'grab'};"
  role="application"
  aria-label={m.galaxy_zoom_hint()}
  onwheel={onWheel}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointercancel={onPointerUp}
>
  {#if galaxy.features.length === 0}
    <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
      <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_features()}</p>
    </div>
  {:else}
    <div
      class="absolute top-0 left-0 origin-top-left"
      style="width: {size}px; height: {size}px; transform: translate({tx}px, {ty}px) scale({scale});"
    >
      <!-- 薄い方眼グリッド（グラフキャンバスの目安。パン/ズームで一緒に動く） -->
      <div
        class="pointer-events-none absolute inset-0 [background-image:linear-gradient(to_right,rgba(100,116,139,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(100,116,139,0.06)_1px,transparent_1px)] [background-size:34px_34px]"
      ></div>

      {#if selected === null}
        <!-- Level 1: 機能間グラフ -->
        <svg class="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100">
          <defs>
            <marker
              id="edge-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="rgba(100,116,139,0.85)" />
            </marker>
          </defs>
          {#each fLines as l (l.a + " " + l.b)}
            <line
              class="graph-el"
              x1={l.x1}
              y1={l.y1}
              x2={l.x2}
              y2={l.y2}
              stroke="rgba(100,116,139,{hovered === null ? 0.5 : edgeActive(l) ? 0.95 : 0.15})"
              stroke-width={edgeActive(l) ? 0.55 : 0.3}
              marker-end="url(#edge-arrow)"
            />
          {/each}
        </svg>

        {#each galaxy.features as f (f.key)}
          {@const p = flayout.get(f.key) ?? FALLBACK}
          <button
            type="button"
            data-node
            class={cn(
              "graph-el absolute -translate-x-1/2 -translate-y-1/2 rounded-xl border px-3 py-2 text-center shadow-sm",
              "hover:ring-2 hover:ring-ring/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              featureClass(f.mastery),
            )}
            style="left: {p.x}%; top: {p.y}%; opacity: {dimmed(fgraph.neighbors, f.key) ? 0.35 : 1};"
            aria-label={f.name}
            onmouseenter={() => (hovered = f.key)}
            onmouseleave={() => (hovered = null)}
            onfocusin={() => (hovered = f.key)}
            onfocusout={() => (hovered = null)}
            onclick={() => openFeature(f.key)}
          >
            <span class="block max-w-36 truncate text-xs font-semibold">{f.name}</span>
            <span class="block text-[10px] opacity-80">
              {formatKc(f.kc)} · {m.galaxy_file_count({ count: f.file_count })}
            </span>
          </button>
        {/each}
      {:else if selectedFile !== null}
        <!-- Level 3: ファイル内の関数コールグラフ（issue 240）。関数は KC を持たないため中立スタイル。 -->
        <svg class="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100">
          <defs>
            <marker
              id="edge-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="rgba(100,116,139,0.85)" />
            </marker>
          </defs>
          {#each fnLines as l (l.a + " " + l.b)}
            <line
              class="graph-el"
              x1={l.x1}
              y1={l.y1}
              x2={l.x2}
              y2={l.y2}
              stroke="rgba(100,116,139,{hovered === null ? 0.5 : edgeActive(l) ? 0.95 : 0.15})"
              stroke-width={edgeActive(l) ? 0.55 : 0.3}
              marker-end="url(#edge-arrow)"
            />
          {/each}
        </svg>

        {#if fnLoading}
          <div class="absolute inset-0 flex items-center justify-center">
            <span class="text-xs text-muted-foreground">{m.common_loading()}</span>
          </div>
        {:else if fnNodes.length === 0}
          <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
            <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_functions()}</p>
          </div>
        {:else}
          {#each fnNodes as fn (fn)}
            {@const p = fnLayout.get(fn) ?? FALLBACK}
            <div
              data-node
              class="graph-el absolute -translate-x-1/2 -translate-y-1/2 rounded-md border border-border bg-muted px-2 py-1 text-center shadow-sm"
              style="left: {p.x}%; top: {p.y}%; opacity: {dimmed(fnGraph.neighbors, fn) ? 0.35 : 1};"
              role="group"
              aria-label={fn}
              onmouseenter={() => (hovered = fn)}
              onmouseleave={() => (hovered = null)}
              onfocusin={() => (hovered = fn)}
              onfocusout={() => (hovered = null)}
            >
              <span class="block max-w-36 truncate font-mono text-[11px] text-foreground">{fn}</span>
            </div>
          {/each}
        {/if}
      {:else if selected !== null}
        <!-- Level 2: 機能の関数レベルグラフ（issue 282）。ファイル=ハブ, 関数=子。CONTAINS+CALLS で接続。 -->
        <svg class="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100">
          <defs>
            <marker
              id="edge-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="rgba(100,116,139,0.85)" />
            </marker>
          </defs>
          {#each featLines as l (l.a + " " + l.b)}
            <line
              class="graph-el"
              x1={l.x1}
              y1={l.y1}
              x2={l.x2}
              y2={l.y2}
              stroke="rgba(100,116,139,{hovered === null ? 0.5 : edgeActive(l) ? 0.95 : 0.15})"
              stroke-width={edgeActive(l) ? 0.55 : 0.3}
              marker-end="url(#edge-arrow)"
            />
          {/each}
        </svg>

        {#if featLoading}
          <div class="absolute inset-0 flex items-center justify-center">
            <span class="text-xs text-muted-foreground">{m.common_loading()}</span>
          </div>
        {:else if featNodes.length === 0}
          <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
            <p class="max-w-sm text-sm text-muted-foreground">{m.galaxy_no_functions()}</p>
          </div>
        {:else}
          {#each featNodes as node (node.id)}
            {@const p = featLayout.get(node.id) ?? FALLBACK}
            {#if node.kind === "file"}
              <!-- ファイルハブ: KC で着色。クリックで Level 3（ファイル内関数グラフ）へドリル。 -->
              <button
                type="button"
                data-node
                class={cn(
                  "graph-el absolute -translate-x-1/2 -translate-y-1/2 rounded-lg border px-2 py-1 text-center shadow-sm",
                  "hover:ring-2 hover:ring-ring/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  hubClass(node.file),
                )}
                style="left: {p.x}%; top: {p.y}%; opacity: {dimmed(featGraph.neighbors, node.id) ? 0.35 : 1};"
                aria-label={node.file}
                onmouseenter={() => (hovered = node.id)}
                onmouseleave={() => (hovered = null)}
                onfocusin={() => (hovered = node.id)}
                onfocusout={() => (hovered = null)}
                onclick={() => openFile(node.file)}
              >
                <span class="block max-w-32 truncate font-mono text-[11px] font-semibold">{node.label}</span>
              </button>
            {:else}
              <!-- 関数ノード: ファイル別の淡い色相でクラスタを見分ける（KC は持たない）。 -->
              <div
                data-node
                class="graph-el absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-1.5 py-0.5 text-center shadow-sm"
                style="left: {p.x}%; top: {p.y}%; opacity: {dimmed(featGraph.neighbors, node.id)
                  ? 0.35
                  : 1}; border-color: hsl({fileHue(node.file)} 45% 55% / 0.7); background-color: hsl({fileHue(
                  node.file,
                )} 45% 55% / 0.12);"
                role="group"
                aria-label={node.label}
                onmouseenter={() => (hovered = node.id)}
                onmouseleave={() => (hovered = null)}
                onfocusin={() => (hovered = node.id)}
                onfocusout={() => (hovered = null)}
              >
                <span class="block max-w-28 truncate font-mono text-[10px] text-foreground">{node.label}</span>
              </div>
            {/if}
          {/each}
          {#if featTruncated}
            <div
              class="pointer-events-none absolute bottom-2 left-2 rounded bg-muted/80 px-2 py-1 text-[10px] text-muted-foreground"
            >
              {m.galaxy_graph_truncated()}
            </div>
          {/if}
        {/if}
      {/if}
    </div>

    <!-- ズーム操作（transform 外。キーボード/クリックでも操作できる導線） -->
    <div data-controls class="absolute right-2 bottom-2 z-10 flex flex-col gap-1">
      <button
        type="button"
        onclick={() => zoomButton(1.25)}
        aria-label={m.galaxy_zoom_in()}
        title={m.galaxy_zoom_in()}
        class="rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground"
      >
        <ZoomIn class="size-4" />
      </button>
      <button
        type="button"
        onclick={() => zoomButton(1 / 1.25)}
        aria-label={m.galaxy_zoom_out()}
        title={m.galaxy_zoom_out()}
        class="rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground"
      >
        <ZoomOut class="size-4" />
      </button>
      <button
        type="button"
        onclick={fit}
        aria-label={m.galaxy_zoom_reset()}
        title={m.galaxy_zoom_reset()}
        class="rounded-md border bg-background/90 p-1.5 text-muted-foreground shadow-sm hover:text-foreground"
      >
        <Maximize class="size-4" />
      </button>
    </div>
  {/if}
</div>

<style>
  /* ホバー時の不透明度・線幅変化をなめらかに。 */
  .graph-el {
    transition:
      opacity 0.15s,
      stroke-width 0.15s;
  }
</style>
