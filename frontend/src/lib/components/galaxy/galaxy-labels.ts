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

// ティール = 知識（明るさ = 被覆度）/ destructive = 危険専用。star-node の cls と 1:1 で一致させる。
// 色だけに頼らず形（リング / 中空 / 破線）でも分岐し、グレースケールでも判別できるようにする（rank10）。
export const masteryDot: Record<MasteryStatus, string> = {
  star: "bg-debt-knowledge shadow-[0_0_6px_2px_rgba(45,212,191,0.5)]",
  dim_star: "bg-debt-knowledge/60 ring-1 ring-inset ring-background/50",
  black_hole: "bg-transparent ring-2 ring-inset ring-destructive",
  unexplored: "border border-dashed border-slate-500 bg-transparent",
};
