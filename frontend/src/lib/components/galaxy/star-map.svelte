<script lang="ts">
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import StarSystem from "./star-system.svelte";
  import { computeForceLayout, type Point } from "./force-layout";
  import { buildGalaxyGraph } from "./galaxy-graph";

  // 2D 星系マップ。星系（モジュール）を実依存グラフの力学レイアウトで配置し、
  // ワームホール（依存）を発光ラインで結ぶ。ノードホバーで関連エッジを強調する（issue 050）。
  const { galaxy }: { galaxy: PersonalGalaxy } = $props();

  let hovered = $state<string | null>(null);

  // 依存グラフ（モジュール集約・隣接・次数）。Map/Set は .ts 側で完結させる。
  const graph = $derived(buildGalaxyGraph(galaxy));
  const degreeOf = (module: string): number => graph.degree.get(module) ?? 0;

  // 決定的フォースレイアウト。systems / wormholes 変化時のみ再計算。
  const layout = $derived(
    computeForceLayout(
      galaxy.systems.map((s) => s.module),
      graph.edges.map((e) => [e.a, e.b] as const),
    ),
  );
  const FALLBACK: Point = { x: 50, y: 50 };
  const posOf = (module: string): Point => layout.get(module) ?? FALLBACK;

  // 描画用エッジ（座標 + 端点モジュール）。
  const lines = $derived(
    graph.edges.map(({ a, b }) => {
      const pa = posOf(a);
      const pb = posOf(b);
      return { a, b, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
    }),
  );

  function edgeActive(l: { a: string; b: string }): boolean {
    return hovered !== null && (l.a === hovered || l.b === hovered);
  }
  function systemDimmed(module: string): boolean {
    if (hovered === null || hovered === module) return false;
    return !(graph.neighbors.get(hovered)?.has(module) ?? false);
  }
  // 次数リングの追加直径(rem)。次数 0 は 0、最大次数で +2.4rem。
  const ringExtra = (module: string): number => (degreeOf(module) / graph.maxDegree) * 2.4;
</script>

<!-- 狭幅では横スクロール（rank30）。内側は正方形にして星(HTML %)とワームホール(SVG viewBox)が
     共有座標系で一緒にリフローする（rank20）。 -->
<div class="h-full min-h-[24rem] overflow-auto rounded-lg bg-slate-950">
  <div class="relative aspect-square min-w-[34rem]">
    <!-- 散らばる星（背景装飾） -->
    <div
      class="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle,rgba(103,232,249,0.12)_1px,transparent_1px)] [background-size:34px_34px]"
    ></div>

    <!-- ワームホール（依存）。from→to を矢印で示し、ノードホバーで関連エッジを強調・他を減衰。 -->
    <svg class="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100">
      <defs>
        <marker
          id="wormhole-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="4"
          markerHeight="4"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="rgba(103,232,249,0.75)" />
        </marker>
      </defs>
      {#each lines as l (l.a + " " + l.b)}
        <line
          class="wormhole"
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke="rgba(103,232,249,{hovered === null ? 0.3 : edgeActive(l) ? 0.85 : 0.07})"
          stroke-width={edgeActive(l) ? 0.55 : 0.28}
          stroke-dasharray="1 1.2"
          marker-end="url(#wormhole-arrow)"
        />
      {/each}
    </svg>

    <!-- 依存次数リング（中心的モジュールほど大きい。色=KC とは別軸の二重符号化）。 -->
    {#each galaxy.systems as system (system.module + "-ring")}
      {@const p = posOf(system.module)}
      {#if ringExtra(system.module) > 0.01}
        <div
          class="wormhole pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-400/25"
          style="left: {p.x}%; top: {p.y}%; width: calc(5rem + {ringExtra(
            system.module,
          )}rem); height: calc(5rem + {ringExtra(system.module)}rem); opacity: {hovered === null ||
          hovered === system.module
            ? 0.55
            : 0.15};"
        ></div>
      {/if}
    {/each}

    <!-- 星系（モジュール）。ホバー/フォーカスで関連エッジを強調し、非関連を減衰。 -->
    {#each galaxy.systems as system (system.module)}
      {@const p = posOf(system.module)}
      <div
        class="wormhole absolute -translate-x-1/2 -translate-y-1/2"
        style="left: {p.x}%; top: {p.y}%; opacity: {systemDimmed(system.module) ? 0.35 : 1};"
        role="group"
        aria-label={system.module}
        onmouseenter={() => (hovered = system.module)}
        onmouseleave={() => (hovered = null)}
        onfocusin={() => (hovered = system.module)}
        onfocusout={() => (hovered = null)}
      >
        <StarSystem {system} />
      </div>
    {/each}
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
