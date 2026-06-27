import * as m from "$lib/paraglide/messages";

export type Priority = "P0" | "P1" | "P2" | "P3";

// 内部の P0–P3 コードを、初見でも分かる一般的な優先度ラベル（最優先 / 高 / 中 / 低）に変換する。
export function priorityLabel(p: Priority): string {
  return {
    P0: m.priority_p0(),
    P1: m.priority_p1(),
    P2: m.priority_p2(),
    P3: m.priority_p3(),
  }[p];
}

// 二軸座標から P0–P3 を導出する（GitLab の手動優先度ラベルではなく座標から機械的に算出）。
// code = code_debt_score / know = 1 - knowledge_coverage（理解の欠落度）。
// 注: 仕様書 §3 の優先度式は code_debt × knowledge_debt × business_impact だが、本フェーズは
// business_impact 未取得のため二軸のしきい値バンドで近似する（本実装で第 3 軸を追加）。
export function derivePriority(code: number, know: number): Priority {
  if (code >= 0.6 && know >= 0.6) return "P0"; // 最危険ゾーン（§2.3 左下）
  if (code >= 0.6 || know >= 0.6) return "P1";
  if (code >= 0.3 || know >= 0.3) return "P2";
  return "P3";
}
