import { describe, expect, it } from "vitest";
import { toFileFunctionGraphData, toFileGraphData } from "./graph-data";
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

  it("filters to a feature's files and drops edges leaving the set", () => {
    const { nodes, links } = toFileGraphData(files, edges, "auth");
    expect(nodes.map((n) => n.id).sort()).toEqual(["a.py", "b.py"]); // c.py は billing のみ → 除外
    expect(links).toEqual([{ source: "a.py", target: "b.py", kind: "calls" }]); // a→c は c 除外で落ちる
  });
});

describe("toFileFunctionGraphData", () => {
  it("builds function nodes + calls links, dropping unknown/self", () => {
    const { nodes, links } = toFileFunctionGraphData(
      ["helper", "inner"],
      [
        { source: "helper", target: "inner" },
        { source: "helper", target: "ghost" }, // unknown → dropped
        { source: "helper", target: "helper" }, // self → dropped
      ],
    );
    expect(nodes.map((n) => n.id).sort()).toEqual(["helper", "inner"]);
    expect(links).toEqual([{ source: "helper", target: "inner", kind: "calls" }]);
  });
});
