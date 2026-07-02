<script lang="ts">
  import { onMount } from "svelte";

  // ログイン系画面の背景: 動くノード‐リンクグラフ（canvas）。参考LP(RepoGraph)の背景を参考にブラッシュアップ
  // ― 暗いネイビーのグラデ地に、teal(#4ecdc4)主体＋シアン/少量アクセントのグローするノードが漂い、近接ノード
  // 同士が線で結ばれる。ログイン中(galaxy force-graph)同様「グラフが動く」印象の装飾。装飾専用（pointer 透過・
  // aria-hidden）。prefers-reduced-motion では 1 フレームだけ描画して静止する。
  let canvas: HTMLCanvasElement;

  type P = { x: number; y: number; vx: number; vy: number; r: number; c: string };

  // LP 参考パレット（teal を厚めに、シアン/ブルー/パープル/アンバーを少量）。
  const PALETTE = ["#4ecdc4", "#4ecdc4", "#4ecdc4", "#4ecdc4", "#7efff5", "#3080ff", "#8d54ff", "#e0a23a"];
  const LINK_RGB = "78,205,196"; // teal（線）
  const LINK_DIST = 150;

  onMount(() => {
    const raw = canvas.getContext("2d");
    if (!raw) return;
    const ctx: CanvasRenderingContext2D = raw; // 以降のクロージャ内で null narrowing を保持

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let w = 0;
    let h = 0;
    let dpr = 1;
    let nodes: P[] = [];

    function seed() {
      const count = Math.min(96, Math.max(30, Math.round((w * h) / 18000)));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        r: 1.2 + Math.random() * 2.0,
        c: PALETTE[Math.floor(Math.random() * PALETTE.length)],
      }));
    }

    function resize() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      // 近接ノードを結ぶ線（距離が近いほど濃く）。
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < LINK_DIST) {
            ctx.strokeStyle = `rgba(${LINK_RGB},${((1 - d / LINK_DIST) * 0.5).toFixed(3)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      // グローするノード。
      for (const n of nodes) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = n.c;
        ctx.shadowColor = n.c;
        ctx.shadowBlur = 8;
        ctx.fill();
      }
      ctx.shadowBlur = 0;
    }

    function step() {
      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > w) n.vx *= -1;
        if (n.y < 0 || n.y > h) n.vy *= -1;
        n.x = Math.max(0, Math.min(w, n.x));
        n.y = Math.max(0, Math.min(h, n.y));
      }
      draw();
      raf = requestAnimationFrame(step);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    if (reduce) draw();
    else step();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  });
</script>

<div class="graph-bg" aria-hidden="true">
  <canvas bind:this={canvas}></canvas>
  <div class="veil"></div>
</div>

<style>
  .graph-bg {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    background: radial-gradient(1200px 760px at 50% 28%, #12203a 0%, #0b1120 55%, #080d1a 100%);
  }
  canvas {
    position: absolute;
    inset: 0;
    display: block;
    height: 100%;
    width: 100%;
  }
  .veil {
    position: absolute;
    inset: 0;
    background: radial-gradient(680px 460px at 50% 46%, rgba(8, 13, 26, 0.72), rgba(8, 13, 26, 0) 72%);
  }
</style>
