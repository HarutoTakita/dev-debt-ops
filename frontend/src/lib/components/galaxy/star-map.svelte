<script lang="ts">
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
  // 機能ノードの色（mastery。star-node の配色と整合）。
  function featureClass(mastery: string): string {
    return (
      {
        star: "border-debt-knowledge bg-debt-knowledge/25 text-debt-knowledge",
        dim_star: "border-debt-knowledge/60 bg-debt-knowledge/10 text-debt-knowledge",
        black_hole: "border-destructive/70 bg-destructive/20 text-destructive",
        unexplored: "border-dashed border-slate-600 bg-slate-900/60 text-slate-300",
      }[mastery] ?? "border-slate-600 bg-slate-900/60 text-slate-300"
    );
  }
</script>

{#if selected !== null && selectedFeature}
  <button
    type="button"
    onclick={() => {
      selected = null;
      hovered = null;
    }}
    class="mb-2 inline-flex items-center gap-1 text-xs font-medium text-cyan-200/80 hover:text-cyan-100"
  >
    ← {selectedFeature.name} · {formatKc(selectedFeature.kc)}
  </button>
{/if}

<!-- 狭幅では横スクロール。内側は正方形にして星(HTML %)と依存線(SVG viewBox)が共有座標系で一緒にリフローする。 -->
<div class="h-full min-h-[24rem] overflow-auto rounded-lg bg-slate-950">
  <div class="relative aspect-square min-w-[34rem]">
    <!-- 散らばる星（背景装飾） -->
    <div
      class="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle,rgba(103,232,249,0.12)_1px,transparent_1px)] [background-size:34px_34px]"
    ></div>

    {#if galaxy.features.length === 0}
      <div class="absolute inset-0 flex items-center justify-center p-6 text-center">
        <p class="max-w-sm text-sm text-slate-400">{m.galaxy_no_features()}</p>
      </div>
    {:else if selected === null}
      <!-- Level 1: 機能間グラフ -->
      <svg class="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100">
        <defs>
          <marker id="edge-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="rgba(103,232,249,0.75)" />
          </marker>
        </defs>
        {#each fLines as l (l.a + " " + l.b)}
          <line
            class="wormhole"
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="rgba(103,232,249,{hovered === null ? 0.3 : edgeActive(l) ? 0.85 : 0.07})"
            stroke-width={edgeActive(l) ? 0.55 : 0.28}
            stroke-dasharray="1 1.2"
            marker-end="url(#edge-arrow)"
          />
        {/each}
      </svg>

      {#each galaxy.features as f (f.key)}
        {@const p = flayout.get(f.key) ?? FALLBACK}
        <button
          type="button"
          class={cn(
            "wormhole absolute -translate-x-1/2 -translate-y-1/2 rounded-2xl border px-3 py-2 text-center backdrop-blur-sm",
            "hover:ring-2 hover:ring-cyan-400/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
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
          <marker id="edge-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="rgba(103,232,249,0.75)" />
          </marker>
        </defs>
        {#each sLines as l (l.a + " " + l.b)}
          <line
            class="wormhole"
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="rgba(103,232,249,{hovered === null ? 0.3 : edgeActive(l) ? 0.85 : 0.07})"
            stroke-width={edgeActive(l) ? 0.55 : 0.28}
            stroke-dasharray="1 1.2"
            marker-end="url(#edge-arrow)"
          />
        {/each}
      </svg>

      {#each sub.files as file (file.path)}
        {@const p = slayout.get(file.path) ?? FALLBACK}
        <div
          class="wormhole absolute -translate-x-1/2 -translate-y-1/2"
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
</div>

<style>
  /* レイアウト/ホバーの不透明度・線幅変化をなめらかに。 */
  .wormhole {
    transition:
      opacity 0.15s,
      stroke-width 0.15s;
  }
</style>
