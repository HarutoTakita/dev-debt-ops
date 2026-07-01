import { describe, expect, it } from "vitest";
import { buildFeatureFunctionGraph } from "./galaxy-graph";

// issue 282: 機能の関数レベルグラフ（file-hub + function, CONTAINS+CALLS）のビルダ。
describe("buildFeatureFunctionGraph", () => {
  const nodes = [
    { id: "file::a.py", label: "a.py", file: "a.py", kind: "file" },
    { id: "a.py::login", label: "login", file: "a.py", kind: "function" },
    { id: "file::b.py", label: "b.py", file: "b.py", kind: "function" }, // kind 検証用（正規化される）
    { id: "b.py::verify", label: "verify", file: "b.py", kind: "function" },
  ];
  const edges = [
    { source: "file::a.py", target: "a.py::login", type: "contains" },
    { source: "a.py::login", target: "b.py::verify", type: "calls" },
    { source: "a.py::login", target: "ghost", type: "calls" }, // 未知ノード → 破棄
  ];

  it("builds a NodeGraph over composite ids, dropping edges to unknown nodes", () => {
    const g = buildFeatureFunctionGraph(nodes, edges);
    // 未知ノード宛て("ghost")は落ち、2 本だけ残る。
    expect(g.edges).toHaveLength(2);
    expect(g.degree.get("a.py::login")).toBe(2); // contains(from hub) + calls(to verify)
    // ノードメタ（label/file/kind）を保持。file 以外の kind は "function" に正規化。
    const byId = new Map(g.nodes.map((n) => [n.id, n]));
    expect(byId.get("file::a.py")?.kind).toBe("file");
    expect(byId.get("file::b.py")?.kind).toBe("function"); // kind が "file" 以外 → function に正規化
    expect(byId.get("a.py::login")?.label).toBe("login");
  });

  it("returns an empty graph for empty input", () => {
    const g = buildFeatureFunctionGraph([], []);
    expect(g.nodes).toEqual([]);
    expect(g.edges).toEqual([]);
  });
});
