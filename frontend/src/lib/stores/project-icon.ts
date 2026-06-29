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

/** 文字列を安定したハッシュ値へ（id から擬似ランダムに色を選ぶ。並べ替え・削除で色がぶれない）。 */
function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/**
 * プロジェクトのアイコン色クラスを返す。
 * 最初に作成された（最古の）プロジェクトはパレット先頭の既存色を維持し、それ以外は id から
 * 安定的に擬似ランダムでパレット[1..] を割り当てる。`projectStore.list`（$state）を読むため
 * `$derived` 内で呼べばリアクティブに追従する。
 */
export function projectIconColor(project: Project): string {
  const list = projectStore.list;
  const oldest = list.reduce<Project | null>(
    (acc, p) => (acc === null || p.created_at < acc.created_at ? p : acc),
    null,
  );
  if (oldest && project.id === oldest.id) return PROJECT_ICON_COLORS[0];
  const rest = PROJECT_ICON_COLORS.length - 1;
  return PROJECT_ICON_COLORS[1 + (hashString(project.id) % rest)];
}
