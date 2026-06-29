<script lang="ts">
  // ログイン中のローディング・スプラッシュ。LP 背景のノード‐リンクグラフ（teal/amber）を薄く敷き、
  // ノードを点滅（twinkle）させつつ中央に「DevDebtOps」を表示する。装飾用途なので軽量に生成。
  let { message = "" }: { message?: string } = $props();

  type Node = { x: number; y: number; r: number; fam: "teal" | "amber"; delay: number; dur: number };
  type Edge = { x1: number; y1: number; x2: number; y2: number };

  const W = 1200;
  const H = 800;

  function build(): { nodes: Node[]; edges: Edge[] } {
    const COUNT = 52;
    const nodes: Node[] = [];
    for (let i = 0; i < COUNT; i++) {
      nodes.push({
        x: 40 + Math.random() * (W - 80),
        y: 40 + Math.random() * (H - 80),
        r: 2.5 + Math.random() * 3.5,
        fam: Math.random() < 0.32 ? "amber" : "teal",
        delay: Math.random() * 3.5,
        dur: 2.2 + Math.random() * 2.8,
      });
    }
    // 各ノードを最近傍 1〜2 個へ結んでネットワーク状に（LP のグラフ構造を簡易再現）。
    const edges: Edge[] = [];
    for (let i = 0; i < COUNT; i++) {
      const near = nodes
        .map((n, j) => ({ j, d: (n.x - nodes[i].x) ** 2 + (n.y - nodes[i].y) ** 2 }))
        .filter((o) => o.j !== i)
        .sort((a, b) => a.d - b.d);
      const k = Math.random() < 0.5 ? 1 : 2;
      for (let m = 0; m < k && m < near.length; m++) {
        const a = nodes[i];
        const b = nodes[near[m].j];
        edges.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y });
      }
    }
    return { nodes, edges };
  }

  const { nodes, edges } = build();
</script>

<div class="splash">
  <svg class="graph" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    {#each edges as e, i (i)}
      <line x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2} class="edge" />
    {/each}
    {#each nodes as n, i (i)}
      <circle
        cx={n.x}
        cy={n.y}
        r={n.r}
        class={`node ${n.fam}`}
        style={`animation-delay:${n.delay}s;animation-duration:${n.dur}s`}
      />
    {/each}
  </svg>

  <div class="veil" aria-hidden="true"></div>

  <div class="content">
    <div class="brand" aria-hidden="true">
      <span class="sq know"></span>
      <span class="sq code"></span>
    </div>
    <h1 class="name">DevDebtOps</h1>
    {#if message}
      <p class="msg">{message}</p>
    {/if}
  </div>
</div>

<style>
  .splash {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    overflow: hidden;
    background: #0c1116;
  }
  .graph {
    position: absolute;
    inset: 0;
    height: 100%;
    width: 100%;
    opacity: 0.42;
  }
  .edge {
    stroke: #2f6a72;
    stroke-width: 1;
    opacity: 0.22;
  }
  .node {
    animation-name: twinkle;
    animation-timing-function: ease-in-out;
    animation-iteration-count: infinite;
  }
  .node.teal {
    fill: #22b8c4;
  }
  .node.amber {
    fill: #e0a23a;
  }
  @keyframes twinkle {
    0%,
    100% {
      opacity: 0.18;
    }
    50% {
      opacity: 1;
    }
  }
  .veil {
    position: absolute;
    inset: 0;
    background: radial-gradient(900px 620px at 50% 46%, rgba(12, 17, 22, 0.66), rgba(12, 17, 22, 0) 70%);
  }
  .content {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    animation: rise 0.6s ease-out both;
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .brand {
    display: flex;
    align-items: center;
  }
  .sq {
    height: 0.9rem;
    width: 0.9rem;
    border-radius: 0.2rem;
  }
  .sq.know {
    background: #22b8c4;
  }
  .sq.code {
    margin-left: -0.3rem;
    background: #e0a23a;
  }
  .name {
    font-size: 2.25rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #f1f5f9;
    animation: glow 3s ease-in-out infinite;
  }
  @keyframes glow {
    0%,
    100% {
      text-shadow: 0 0 18px rgba(34, 184, 196, 0.25);
    }
    50% {
      text-shadow: 0 0 26px rgba(34, 184, 196, 0.55);
    }
  }
  .msg {
    font-size: 0.875rem;
    color: #94a3b8;
  }
  @media (prefers-reduced-motion: reduce) {
    .node {
      animation: none;
      opacity: 0.5;
    }
    .name {
      animation: none;
    }
    .content {
      animation: none;
    }
  }
</style>
