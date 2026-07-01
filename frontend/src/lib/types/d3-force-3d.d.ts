// `d3-force-3d` ships no types and `@types/d3-force-3d` doesn't exist on npm (404). We only use
// `forceCollide` (to add a collision force to force-graph's internal simulation so nodes never
// overlap). Minimal ambient declaration — generic node type keeps the radius accessor type-safe and
// the returned force is structurally assignable to force-graph's loose `ForceFn`.
declare module "d3-force-3d" {
  export interface ForceCollide<N> {
    (alpha: number): void;
    initialize?: (nodes: N[], ...args: unknown[]) => void;
    radius(r: number | ((node: N, i: number, nodes: N[]) => number)): ForceCollide<N>;
    strength(s: number): ForceCollide<N>;
    iterations(n: number): ForceCollide<N>;
  }
  export function forceCollide<N = unknown>(
    radius?: number | ((node: N, i: number, nodes: N[]) => number),
  ): ForceCollide<N>;
}
