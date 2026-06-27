import { describe, expect, it } from "vitest";
import { computeForceLayout, type Point } from "./force-layout";

function at(pos: Map<string, Point>, id: string): Point {
  const p = pos.get(id);
  if (!p) throw new Error(`missing position for ${id}`);
  return p;
}
const dist = (p: Point, q: Point) => Math.hypot(p.x - q.x, p.y - q.y);

describe("computeForceLayout", () => {
  it("returns an empty map for no nodes", () => {
    expect(computeForceLayout([], []).size).toBe(0);
  });

  it("centers a single node", () => {
    expect(at(computeForceLayout(["a"], []), "a")).toEqual({ x: 50, y: 50 });
  });

  it("is deterministic (no Math.random): same input → same layout", () => {
    const nodes = ["a", "b", "c", "d"];
    const edges: [string, string][] = [
      ["a", "b"],
      ["b", "c"],
    ];
    const first = computeForceLayout(nodes, edges);
    const second = computeForceLayout(nodes, edges);
    for (const id of nodes) {
      expect(at(second, id)).toEqual(at(first, id));
    }
  });

  it("keeps every node inside the padded box", () => {
    const nodes = ["a", "b", "c", "d", "e", "f"];
    const edges: [string, string][] = [
      ["a", "b"],
      ["a", "c"],
      ["a", "d"],
      ["e", "f"],
    ];
    const padding = 12;
    const pos = computeForceLayout(nodes, edges, { padding });
    for (const id of nodes) {
      const p = at(pos, id);
      expect(p.x).toBeGreaterThanOrEqual(padding);
      expect(p.x).toBeLessThanOrEqual(100 - padding);
      expect(p.y).toBeGreaterThanOrEqual(padding);
      expect(p.y).toBeLessThanOrEqual(100 - padding);
    }
  });

  it("places connected nodes closer than unconnected ones", () => {
    // a–b connected; c isolated. The spring should pull a,b nearer to each other
    // than the isolated c sits to either.
    const pos = computeForceLayout(["a", "b", "c"], [["a", "b"]]);
    const a = at(pos, "a");
    const b = at(pos, "b");
    const c = at(pos, "c");
    expect(dist(a, b)).toBeLessThan(dist(a, c));
    expect(dist(a, b)).toBeLessThan(dist(b, c));
  });

  it("ignores self-loops and unknown endpoints without throwing", () => {
    const pos = computeForceLayout(
      ["a", "b"],
      [
        ["a", "a"], // self-loop
        ["a", "ghost"], // unknown endpoint
        ["a", "b"],
      ],
    );
    expect(pos.size).toBe(2);
  });
});
