// confidence（解析の確信度）→ バッジクラスの写像。
// DevDebtOps Twin パレットの「地層アンバー（debt-code）」で濃淡を表現し、GitLab 紫は使わない。
// high = 実線・濃色 / medium = 淡色 / low = 点線枠 の三段階で確信度が一目で分かるようにする。
export type Confidence = "high" | "medium" | "low";

export const confidenceBadge: Record<Confidence, string> = {
  high: "bg-debt-code/20 text-debt-code ring-1 ring-debt-code/40 font-medium",
  medium: "bg-debt-code/10 text-debt-code/90",
  low: "border border-dashed border-debt-code/40 text-muted-foreground",
};
