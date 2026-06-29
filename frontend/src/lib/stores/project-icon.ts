import type { Project } from "$lib/api/schemas";
import { project as projectStore } from "$lib/stores/project-store.svelte";

/**
 * プロジェクトアイコンの色（背景 + 文字）。完全な Tailwind クラス名で持つ
 * （JIT 生成のため動的合成しない。SECTION_ICON_COLORS と同じ方針）。
 * 先頭は既存のプロジェクト色（最初に作成されたプロジェクトが維持する）。
 */
export const PROJECT_ICON_COLORS = [
  "bg-debt-knowledge/15 text-debt-knowledge", // 既定（最初のプロジェクト）
  "bg-debt-code/15 text-debt-code",
  "bg-emerald-500/15 text-emerald-500",
  "bg-sky-500/15 text-sky-500",
  "bg-violet-500/15 text-violet-500",
  "bg-rose-500/15 text-rose-500",
  "bg-amber-500/15 text-amber-500",
  "bg-teal-500/15 text-teal-500",
];

/**
 * プロジェクトのアイコン色クラスを返す。
 * 作成順（古い順）でパレットを巡回して割り当てる（セクションの色方式と同じ）。最古 =
 * パレット先頭の既存色。これにより先頭から PROJECT_ICON_COLORS.length 件までは色が重複しない。
 * `projectStore.list`（$state）を読むため `$derived` 内で呼べばリアクティブに追従する。
 */
export function projectIconColor(project: Project): string {
  const ordered = [...projectStore.list].sort((a, b) => {
    if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1;
    return a.id < b.id ? -1 : 1; // created_at 同値時の安定タイブレーク
  });
  const idx = ordered.findIndex((p) => p.id === project.id);
  return PROJECT_ICON_COLORS[(idx < 0 ? 0 : idx) % PROJECT_ICON_COLORS.length];
}
