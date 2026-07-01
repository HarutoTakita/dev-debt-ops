<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { neighborsOf, type GraphLink, type GraphNode } from "./graph-data";

  // 理解度マップの力学グラフを canvas で描画する再利用ラッパ（issue 284）。force-graph（d3-force ベース）を
  // 使い、d3-force-3d の forceCollide で衝突回避＝ノードが重ならない。ドラッグ/ズーム/パン/ホバーは
  // ライブラリ標準。SSR/prerender 回避のため force-graph は onMount 内で動的 import する。
  // 破壊的変更対策: 親から渡る nodes/links は毎回新規プレーンオブジェクト（graph-data.ts が保証）。
  type ForceGraphInstance = import("force-graph").default<GraphNode, GraphLink>;
  type ZoomControls = { zoomIn: () => void; zoomOut: () => void; fit: () => void };

  let {
    nodes,
    links,
    onNodeClick,
    onNodeHover,
    bindControls,
  }: {
    nodes: GraphNode[];
    links: GraphLink[];
    onNodeClick?: (node: GraphNode) => void;
    onNodeHover?: (node: GraphNode | null) => void;
    bindControls?: (controls: ZoomControls) => void; // ズーム操作を親へ公開（親のボタンから呼ぶ）
  } = $props();

  let container: HTMLDivElement;
  let cw = $state(0);
  let ch = $state(0);
  let graph: ForceGraphInstance | null = null;

  // ホバー中のノード id とその近傍集合（減光/強調用）。Set 構築は graph-data.ts(neighborsOf) に閉じる。
  let hoveredId: string | null = null;
  let neighborIds: Set<string> = neighborsOf(null, [], linkEnd);

  // KC 状態 → 色（凡例 galaxy-legend の masteryDot に対応）。canvas 安全な固定色で確実に色分けする（issue 290）。
  const MASTERY_COLOR: Record<string, string> = {
    star: "#14b8a6", // 完全理解（ティール）
    dim_star: "#5eead4", // 部分理解（淡いティール）
    black_hole: "#ef4444", // 未理解（赤）
    unexplored: "#94a3b8", // 未着手（グレー）
  };
  const DIM_COLOR = "rgba(148,163,184,0.25)"; // ホバー時の非近傍ノード（減光）
  let labelColor = "#334155"; // ラベル文字色（テーマの --foreground を解決）
  function resolveLabelColor() {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--foreground").trim();
    if (v) labelColor = v;
  }
  function nodeColor(node: GraphNode): string {
    if (hoveredId && node.id !== hoveredId && !neighborIds.has(node.id)) return DIM_COLOR; // 減光
    return MASTERY_COLOR[node.mastery ?? "unexplored"] ?? MASTERY_COLOR.unexplored;
  }
  function nodeRadius(node: GraphNode): number {
    return Math.sqrt(node.val) * (graph?.nodeRelSize() ?? 4);
  }
  function linkColor(link: GraphLink): string {
    const incident = hoveredId != null && (linkEnd(link.source) === hoveredId || linkEnd(link.target) === hoveredId);
    if (hoveredId && !incident) return "rgba(100,116,139,0.12)";
    if (incident) return "rgba(100,116,139,0.9)";
    return link.kind === "calls" ? "rgba(100,116,139,0.55)" : "rgba(100,116,139,0.3)";
  }
  // force-graph は link.source/target を id→ノード参照へ書き換えるため両対応で id を取り出す。
  function linkEnd(end: unknown): string {
    if (typeof end === "object" && end !== null) return String((end as { id?: unknown }).id ?? "");
    return String(end ?? "");
  }

  function recomputeNeighbors() {
    neighborIds = neighborsOf(hoveredId, links, linkEnd);
  }

  onMount(() => {
    let disposed = false;
    (async () => {
      const [{ default: ForceGraph }, { forceCollide }] = await Promise.all([
        import("force-graph"),
        import("d3-force-3d"),
      ]);
      if (disposed) return;
      resolveLabelColor();
      const g = new ForceGraph<GraphNode, GraphLink>(container)
        .nodeId("id")
        .nodeRelSize(4)
        .nodeVal((n) => n.val)
        .nodeLabel((n) => n.label)
        .nodeColor(nodeColor)
        .linkColor(linkColor)
        .linkWidth((l) =>
          hoveredId != null && (linkEnd(l.source) === hoveredId || linkEnd(l.target) === hoveredId) ? 2 : 1,
        )
        .linkDirectionalArrowLength((l) => (l.kind === "calls" ? 3 : 0))
        .linkDirectionalArrowRelPos(1)
        .onNodeClick((n) => onNodeClick?.(n))
        .onNodeHover((n) => {
          hoveredId = n ? n.id : null;
          recomputeNeighbors();
          onNodeHover?.(n);
        })
        .onEngineStop(() => g.zoomToFit(400, 40));
      // ラベルはズームインした時だけ描画（過密回避）。ノード円は既定描画に任せ 'after' で重ねる。
      g.nodeCanvasObjectMode(() => "after").nodeCanvasObject((node, ctx, scale) => {
        if (scale < 1.3) return;
        const label = node.label.length > 24 ? node.label.slice(0, 23) + "…" : node.label;
        const fontSize = 10 / scale;
        ctx.font = `${fontSize}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = labelColor;
        ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + nodeRadius(node) + 1 / scale);
      });
      // ノード円を明示的にポインタ判定領域として塗る（issue 286）。custom nodeCanvasObject を設定すると
      // クリック判定がそれに由来し、ラベルはズーム時のみ描画のため既定ズームでは判定領域が空になり
      // 「ノードが見えるのにクリックできない＝機能クリックでドリルしない」不具合になる。円で判定域を確定する。
      g.nodePointerAreaPaint((node, color, ctx) => {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, nodeRadius(node), 0, 2 * Math.PI);
        ctx.fill();
      });
      g.d3Force("collide", forceCollide<GraphNode>((n) => nodeRadius(n) + 3).strength(1));
      g.width(cw || container.clientWidth).height(ch || container.clientHeight);
      g.graphData({ nodes, links });
      graph = g;
      bindControls?.({
        zoomIn: () => graph?.zoom((graph?.zoom() ?? 1) * 1.25, 250),
        zoomOut: () => graph?.zoom((graph?.zoom() ?? 1) * 0.8, 250),
        fit: () => graph?.zoomToFit(400, 40),
      });
    })();

    // テーマ切替（document.documentElement の class 変化）で配色を再解決し再描画。
    const themeObserver = new MutationObserver(() => {
      resolveLabelColor();
      graph?.graphData(graph.graphData()); // 再描画をトリガ
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      disposed = true;
      themeObserver.disconnect();
    };
  });

  onDestroy(() => {
    graph?.pauseAnimation();
    graph?._destructor();
    graph = null;
  });

  // データ差し替え（フィルタ/レベル変更）で graphData を再投入し再描画。インスタンスは再生成しない。
  // graphData だけだと停止済みシミュレーションが再計算されず表示が変わらないことがあるため、明示的に
  // 再加熱＋アニメ再開して確実にレイアウト/描画を更新する（issue 290: 機能フィルタが効かない不具合）。
  $effect(() => {
    hoveredId = null;
    neighborIds = neighborsOf(null, [], linkEnd);
    if (!graph) return;
    graph.graphData({ nodes, links });
    graph.d3ReheatSimulation();
    graph.resumeAnimation();
  });

  // リサイズ反映。
  $effect(() => {
    if (cw > 0 && ch > 0) graph?.width(cw).height(ch);
  });
</script>

<div bind:this={container} bind:clientWidth={cw} bind:clientHeight={ch} class="size-full"></div>
