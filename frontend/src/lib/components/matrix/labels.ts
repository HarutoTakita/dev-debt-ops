import type { DebtItem, Severity } from "$lib/api/schemas";
import * as m from "$lib/paraglide/messages";

// 負債の各 enum 値 → i18n ラベルの写像（行 / メタパネル / バッジで共用）。
export function categoryLabel(d: DebtItem): string {
  if (d.kind === "code") {
    return {
      duplicate: m.debt_type_duplicate(),
      dead: m.debt_type_dead(),
      complexity: m.debt_type_complexity(),
      other: m.debt_type_other(),
    }[d.type];
  }
  return {
    ai_generated: m.debt_reason_ai_generated(),
    author_left: m.debt_reason_author_left(),
    no_review: m.debt_reason_no_review(),
    other: m.debt_reason_other(),
  }[d.reason];
}

export function severityLabel(s: Severity): string {
  return {
    critical: m.severity_critical(),
    high: m.severity_high(),
    medium: m.severity_medium(),
    low: m.severity_low(),
  }[s];
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    open: m.status_open(),
    in_pr: m.status_in_pr(),
    in_progress: m.status_in_progress(),
    resolved: m.status_resolved(),
    dismissed: m.status_dismissed(),
  };
  return map[status] ?? status;
}

export function kindLabel(kind: DebtItem["kind"]): string {
  return kind === "code" ? m.kind_code() : m.kind_knowledge();
}

export function agentLabel(agent: string): string {
  return agent === "code_debt" ? m.agent_code_debt() : m.agent_knowledge_debt();
}
