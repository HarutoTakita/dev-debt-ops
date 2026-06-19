<script lang="ts">
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import StarSystem from "./star-system.svelte";

  // 2D 星系マップ。暗い宇宙背景に星系を配置し、ワームホール（依存）を発光ラインで結ぶ。
  const { galaxy }: { galaxy: PersonalGalaxy } = $props();

  // 星系の配置（% 座標）。DOM 計測を避け、決定的なプリセット位置を index で割り当てる。
  const POS = [
    { x: 26, y: 30 },
    { x: 72, y: 26 },
    { x: 24, y: 72 },
    { x: 76, y: 70 },
    { x: 50, y: 50 },
    { x: 50, y: 86 },
    { x: 86, y: 50 },
    { x: 14, y: 50 },
  ];
  const posOf = (i: number) => POS[i % POS.length];

  const moduleIndex = $derived(new Map(galaxy.systems.map((s, i) => [s.module, i])));

  function moduleOf(path: string): string | undefined {
    return galaxy.systems.find((s) => s.files.some((f) => f.path === path))?.module;
  }

  // ワームホールを星系間（モジュール間）の発光ラインに変換。同一星系内・解決不能は除外。
  const lines = $derived(
    galaxy.wormholes
      .map((w) => {
        const a = moduleOf(w.from);
        const b = moduleOf(w.to);
        if (!a || !b || a === b) return null;
        const ia = moduleIndex.get(a);
        const ib = moduleIndex.get(b);
        if (ia === undefined || ib === undefined) return null;
        const pa = posOf(ia);
        const pb = posOf(ib);
        return { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y };
      })
      .filter((l): l is { x1: number; y1: number; x2: number; y2: number } => l !== null),
  );
</script>

<!-- 狭幅では横スクロール（rank30）。内側は正方形にして星(HTML %)とワームホール(SVG viewBox)が
     共有座標系で一緒にリフローする（rank20）。 -->
<div class="h-full min-h-[24rem] overflow-auto rounded-lg bg-slate-950">
  <div class="relative aspect-square min-w-[34rem]">
    <!-- 散らばる星（背景装飾） -->
    <div
      class="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle,rgba(103,232,249,0.12)_1px,transparent_1px)] [background-size:34px_34px]"
    ></div>

    <!-- ワームホール（依存）。from→to を矢印で示し、線ごとにホバーで強調する。 -->
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
      {#each lines as l, i (i)}
        <!-- 透明な太い当たり判定線（ホバー領域を確保） -->
        <line class="wormhole-hit" x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="transparent" stroke-width="2.5" />
        <!-- 可視線（隣接の当たり判定線がホバーされると強調） -->
        <line
          class="wormhole"
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke="rgba(103,232,249,0.28)"
          stroke-width="0.28"
          stroke-dasharray="1 1.2"
          marker-end="url(#wormhole-arrow)"
        />
      {/each}
    </svg>

    <!-- 星系（モジュール） -->
    {#each galaxy.systems as system, i (system.module)}
      <div class="absolute -translate-x-1/2 -translate-y-1/2" style="left: {posOf(i).x}%; top: {posOf(i).y}%;">
        <StarSystem {system} />
      </div>
    {/each}
  </div>
</div>

<style>
  /* 当たり判定線のみホバー可能にし、隣接する可視線を強調（他線はミュートのまま）。 */
  .wormhole-hit {
    pointer-events: stroke;
  }
  .wormhole {
    transition:
      opacity 0.15s,
      stroke-width 0.15s;
  }
  .wormhole-hit:hover + .wormhole {
    opacity: 1;
    stroke-width: 0.55;
  }
</style>
