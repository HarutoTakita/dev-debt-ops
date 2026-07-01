import { describe, expect, it } from "vitest";
import { toFeatureFunctionGraphData, toFeatureGraphData, toFileFunctionGraphData } from "./graph-data";
import type { FeatureNode, FileMastery } from "$lib/api/schemas";

// issue 284: ドメイン → force-graph {nodes,links} 変換。純粋・決定的（描画自体は canvas で別途）。
describe("graph-data transforms", () => {
  it("toFeatureGraphData maps features to nodes + feature links", () => {
    const features: FeatureNode[] = [
      { key: "auth", name: "Auth", kc: 0.5, mastery: "star", file_count: 3 },
      { key: "billing", name: "Billing", kc: 0.2, mastery: "black_hole", file_count: 2 },
    ];
    const { nodes, links } = toFeatureGraphData(features, [{ from: "auth", to: "billing" }]);
    expect(nodes.map((n) => n.id).sort()).toEqual(["auth", "billing"]);
    expect(nodes.every((n) => n.kind === "feature")).toBe(true);
    expect(links).toEqual([{ source: "auth", target: "billing", kind: "feature" }]);
  });

  it("toFeatureFunctionGraphData keeps kind + link type, colors file-hub by KC, sizes by degree", () => {
    const featNodes = [
      { id: "file::a.py", label: "a.py", file: "a.py", kind: "file" },
      { id: "a.py::login", label: "login", file: "a.py", kind: "function" },
      { id: "file::b.py", label: "b.py", file: "b.py", kind: "file" },
      { id: "b.py::verify", label: "verify", file: "b.py", kind: "function" },
    ];
    const featEdges = [
      { source: "file::a.py", target: "a.py::login", type: "contains" as const },
      { source: "file::b.py", target: "b.py::verify", type: "contains" as const },
      { source: "a.py::login", target: "b.py::verify", type: "calls" as const },
    ];
    const fileMap = new Map<string, FileMastery>([
      ["a.py", { path: "a.py", module: "m", kc: 0.9, mastery: "star", mastered: true, feature_keys: [] }],
    ]);
    const { nodes, links } = toFeatureFunctionGraphData(featNodes, featEdges, fileMap);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    expect(byId.get("file::a.py")?.mastery).toBe("star"); // file-hub colored by KC
    expect(byId.get("file::b.py")?.mastery).toBeUndefined(); // not in fileMap → no mastery
    expect(byId.get("a.py::login")?.mastery).toBeUndefined(); // functions carry no KC
    // link kinds preserved (contains vs calls) for arrow styling.
    expect(links).toContainEqual({ source: "a.py::login", target: "b.py::verify", kind: "calls" });
    expect(links.filter((l) => l.kind === "contains")).toHaveLength(2);
    // degree scaling: login has degree 2 (contains + calls), verify degree 2 as well; hub a.py degree 1.
    expect(byId.get("a.py::login")!.val).toBeGreaterThan(byId.get("file::a.py")!.val - 100); // sanity: numbers
  });

  it("toFileFunctionGraphData builds function nodes + calls links, dropping unknowns/self", () => {
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
