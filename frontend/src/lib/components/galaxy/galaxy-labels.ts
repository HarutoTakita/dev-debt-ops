import type { MasteryStatus } from "$lib/api/schemas";
import * as m from "$lib/paraglide/messages";

// 星域メタファーのラベルと、リスト/凡例で使う色ドット。
export function masteryLabel(s: MasteryStatus): string {
  return {
    star: m.galaxy_status_star(),
    dim_star: m.galaxy_status_dim_star(),
    black_hole: m.galaxy_status_black_hole(),
    unexplored: m.galaxy_status_unexplored(),
  }[s];
}

export const masteryDot: Record<MasteryStatus, string> = {
  star: "bg-cyan-300 shadow-[0_0_6px_2px_rgba(103,232,249,0.7)]",
  dim_star: "bg-teal-400/70",
  black_hole: "bg-red-500",
  unexplored: "border border-dashed border-slate-500 bg-transparent",
};
