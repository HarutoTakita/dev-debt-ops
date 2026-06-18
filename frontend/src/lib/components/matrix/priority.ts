export type Priority = "P0" | "P1" | "P2" | "P3";

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
