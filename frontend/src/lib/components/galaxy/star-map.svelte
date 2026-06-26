<script lang="ts">
  import ZoomIn from "@lucide/svelte/icons/zoom-in";
  import ZoomOut from "@lucide/svelte/icons/zoom-out";
  import Maximize from "@lucide/svelte/icons/maximize";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import StarNode from "./star-node.svelte";
  import { computeForceLayout, type Point } from "./force-layout";
  import { buildFeatureGraph, buildFileSubgraph } from "./galaxy-graph";
  import { formatKc } from "$lib/format/kc";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 2 段の理解度マップ（issue 065）。Level 1 = 機能（feature）ノード + 機能間グラフ。機能クリックで
  // Level 2（その機能の構成ファイルの依存グラフ）へインプレースズーム。「← 戻る」で Level 1 に戻る。
  // Map/Set の構築は galaxy-graph.ts / force-layout.ts（.ts 側）で完結させる（prefer-svelte-reactivity）。
  const { galaxy }: { galaxy: PersonalGalaxy } = $props();

  let selected = $state<string | null>(null); // 選択中の feature key（null = Level 1）
  let hovered = $state<string | null>(null);

  const selectedFeature = $derived(galaxy.features.find((f) => f.key === selected) ?? null);
  // データ更新で選択中の機能が消えたら Level 1 に戻す。
  $effect(() => {
    if (selected !== null && !galaxy.features.some((f) => f.key === selected)) selected = null;
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

  // --- Level 2: 機能内ファイルグラフ ---
  const sub = $derived(selected ? buildFileSubgraph(galaxy, selected) : null);
  const slayout = $derived(
    computeForceLayout(sub ? sub.files.map((f) => f.path) : [], sub ? sub.edges.map((e) => [e.a, e.b] as const) : []),
  );
  const sLines = $derived(
    sub
      ? sub.edges.map(({ a, b }) => {
          const pa = slayout.get(a) ?? FALLBACK;
          const pb = slayout.get(b) ?? FALLBACK;
          return { a, b, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
        })
      : [],
  );

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
    const trigger = `${selected}:${size}`;
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

{#if selected !== null && selectedFeature}
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
            onclick={() => {
              selected = f.key;
              hovered = null;
            }}
          >
            <span class="block max-w-36 truncate text-xs font-semibold">{f.name}</span>
            <span class="block text-[10px] opacity-80">
              {formatKc(f.kc)} · {m.galaxy_file_count({ count: f.file_count })}
            </span>
          </button>
        {/each}
      {:else if sub}
        <!-- Level 2: 機能内ファイル依存グラフ -->
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
          {#each sLines as l (l.a + " " + l.b)}
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

        {#each sub.files as file (file.path)}
          {@const p = slayout.get(file.path) ?? FALLBACK}
          <div
            data-node
            class="graph-el absolute -translate-x-1/2 -translate-y-1/2"
            style="left: {p.x}%; top: {p.y}%; opacity: {dimmed(sub.neighbors, file.path) ? 0.35 : 1};"
            role="group"
            aria-label={file.path}
            onmouseenter={() => (hovered = file.path)}
            onmouseleave={() => (hovered = null)}
            onfocusin={() => (hovered = file.path)}
            onfocusout={() => (hovered = null)}
          >
            <StarNode {file} />
          </div>
        {/each}
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
