// agent_trace（[call]/[done]/[summary] toolname …）を人間可読なステップキーへ写像する純粋関数。
// i18n（m.*）はこのキーを使う側（tech-stack-panel）で行うため、ここは Paraglide 非依存にしておく
// （ストアのユニットテストを軽くするため）。

export type StackStep = "analyzing" | "listing" | "reading" | "classifying" | "saving";

const TOOL_TO_STEP: Record<string, StackStep> = {
  list_key_files: "listing",
  read_file: "reading",
  classify_stack: "classifying",
  save_stack: "saving",
};

// 最新の trace 行からステップキーを判定する。判定不能（空・summary など）は "analyzing"。
export function traceToStep(trace: string[]): StackStep {
  const last = trace.at(-1);
  if (!last) return "analyzing";
  const match = last.match(/^\[(?:call|done)\]\s+(\w+)/);
  if (match) {
    return TOOL_TO_STEP[match[1]] ?? "analyzing";
  }
  return "analyzing";
}
