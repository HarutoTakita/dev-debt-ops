import { describe, expect, it } from "vitest";
import { toFileGraphData } from "./graph-data";
import type { FileMastery } from "$lib/api/schemas";

// issue 288: ドメイン → force-graph {nodes,links} 変換。純粋・決定的（描画自体は canvas で別途）。
function file(path: string, feature_keys: string[] = [], mastery: FileMastery["mastery"] = "star"): FileMastery {
  return { path, module: path.split("/")[0], kc: 0.5, mastery, mastered: false, feature_keys };
}

describe("toFileGraphData", () => {
  const files = [file("a.py", ["auth"]), file("b.py", ["auth"]), file("c.py", ["billing"])];
  const edges = [
    { source: "a.py", target: "b.py" },
    { source: "a.py", target: "c.py" },
    { source: "a.py", target: "ghost" }, // 未知端点 → 落ちる
  ];

  it("builds file nodes + file edges over the whole project when featureKey is null", () => {
    const { nodes, links } = toFileGraphData(files, edges, null);
    expect(nodes.map((n) => n.id).sort()).toEqual(["a.py", "b.py", "c.py"]);
    expect(nodes.every((n) => n.kind === "file")).toBe(true);
    expect(nodes.find((n) => n.id === "a.py")?.label).toBe("a.py"); // basename ラベル
    expect(links).toHaveLength(2); // a→b, a→c（a→ghost は除外）
    expect(links.every((l) => l.kind === "calls")).toBe(true);
  });

  it("expands a feature filter to its graph neighborhood (includes related files)", () => {
    // seed = auth の {a.py, b.py}。a.py の隣接 c.py（billing）もグラフ 1 ホップで含める（関連コード）。
    const { nodes, links } = toFileGraphData(files, edges, "auth");
    expect(nodes.map((n) => n.id).sort()).toEqual(["a.py", "b.py", "c.py"]);
    const calls = links
      .filter((l) => l.kind === "calls")
      .map((l) => `${l.source}->${l.target}`)
      .sort();
    expect(calls).toEqual(["a.py->b.py", "a.py->c.py"]);
  });

  it("drops unknown/self edges", () => {
    const { links } = toFileGraphData(
      [file("a.py"), file("b.py")],
      [
        { source: "a.py", target: "b.py" },
        { source: "a.py", target: "ghost" }, // unknown → dropped
        { source: "a.py", target: "a.py" }, // self → dropped
      ],
      null,
    );
    expect(links).toEqual([{ source: "a.py", target: "b.py", kind: "calls" }]);
  });

  it("connects isolated nodes to their nearest sibling (no isolated node remains)", () => {
    // エッジ無し → 本来は全ノード孤立。sibling エッジで最も近い（同ディレクトリ優先）ノードへつなぐ。
    const { nodes, links } = toFileGraphData([file("dir/x.py"), file("dir/y.py"), file("other/z.py")], [], null);
    expect(nodes).toHaveLength(3);
    const deg = new Map<string, number>();
    for (const l of links) {
      deg.set(l.source, (deg.get(l.source) ?? 0) + 1);
      deg.set(l.target, (deg.get(l.target) ?? 0) + 1);
    }
    expect(nodes.every((n) => (deg.get(n.id) ?? 0) >= 1)).toBe(true); // 孤立ノードなし
    expect(links.some((l) => l.kind === "sibling")).toBe(true);
  });
});
