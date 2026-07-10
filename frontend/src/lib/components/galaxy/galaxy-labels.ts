import type { MasteryStatus } from "$lib/api/schemas";
import * as m from "$lib/paraglide/messages";

// 理解度ステータスのラベルと、リスト/凡例で使う色ドット。
export function masteryLabel(s: MasteryStatus): string {
  return {
    star: m.galaxy_status_star(),
    dim_star: m.galaxy_status_dim_star(),
    black_hole: m.galaxy_status_black_hole(),
    unexplored: m.galaxy_status_unexplored(),
    out_of_scope: m.galaxy_status_out_of_scope(),
  }[s];
}

// 理解度を色で表す（ティール=理解済み/部分理解、赤=未理解、グレー破線=未着手、淡い塗り=対象外）。
// 色だけに頼らず形（塗り / リング / 中空 / 破線）でも分岐し、グレースケールでも判別できるようにする。
export const masteryDot: Record<MasteryStatus, string> = {
  star: "bg-debt-knowledge",
  dim_star: "bg-debt-knowledge/50 ring-1 ring-inset ring-debt-knowledge",
  black_hole: "bg-transparent ring-2 ring-inset ring-destructive",
  unexplored: "border border-dashed border-muted-foreground bg-transparent",
  out_of_scope: "bg-muted-foreground/30", // 学習対象外: 淡い塗り（未着手の破線とは別形）
};
