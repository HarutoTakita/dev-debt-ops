import Activity from "@lucide/svelte/icons/activity";
import Sparkles from "@lucide/svelte/icons/sparkles";
import Grid3x3 from "@lucide/svelte/icons/grid-3x3";
import GraduationCap from "@lucide/svelte/icons/graduation-cap";
import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
import Settings from "@lucide/svelte/icons/settings";
import type { Pathname } from "$app/types";
import { galaxy } from "$lib/stores/galaxy-store.svelte";
import { quiz } from "$lib/stores/quiz-store.svelte";
import { MOCK_DEBTS } from "$lib/api/mock/debts";
import * as m from "$lib/paraglide/messages";

// すべての lucide アイコンは同一のコンポーネント型を共有するため、1 つから型を借りる。
export type IconComponent = typeof Activity;

// メニューはプロジェクト（= 観測対象リポジトリ）単位にスコープされる。
export type NavContext = { orgSlug: string; projectSlug: string; projectSelected: boolean };

export interface NavItem {
  id: string;
  /** i18n ラベル（Paraglide メッセージ関数）。呼び出し時に現在ロケールで解決される。 */
  label: () => string;
  /** プロジェクト相対パス（resolve() に渡せる Pathname） */
  route: (ctx: NavContext) => Pathname;
  icon: IconComponent;
  /** プロジェクトルート（Overview）など完全一致でアクティブ判定する項目 */
  exact?: boolean;
  /** 未実装機能: ナビ枠だけ用意し、ルートは Coming Soon プレースホルダへ向ける */
  comingSoon?: boolean;
  /** 有効条件（例: Repos は接続済みのみ活性） */
  enabled?: (ctx: NavContext) => boolean;
  /** KC% / 未返済負債残高など（本 issue ではダミー固定値） */
  pill?: (ctx: NavContext) => string | null;
  /** ピン留め可否（デフォルト true） */
  pinnable?: boolean;
}

export interface NavSection {
  id: string;
  /** null は見出しなしの最終セクション（Settings 等） */
  label: (() => string) | null;
  items: NavItem[];
}

// add_menu 順 = 表示順。understand 系（理解する / 返済する）を上位に、Repos（コード閲覧）は参照として末尾へ。
// 各ルートは /[org]/[project]/... のプロジェクト相対パス。プロジェクト切替でメニューの主語が切り替わる。
export const navSections: NavSection[] = [
  {
    id: "understand",
    label: m.nav_section_understand,
    items: [
      {
        id: "overview",
        label: m.nav_overview,
        icon: Activity,
        exact: true,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}`,
      },
      {
        id: "galaxy",
        label: m.nav_galaxy,
        icon: Sparkles,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}/galaxy`,
        comingSoon: true,
        // 星域観測済み（モック有効）なら自分の KC% を pill 表示、未観測なら非表示
        pill: () => (galaxy.myKc !== null ? `${galaxy.myKc}%` : null),
      },
      {
        id: "matrix",
        label: m.nav_matrix,
        icon: Grid3x3,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}/matrix`,
        // 未返済の負債件数（モック）をデータから導出。0 件なら pill 非表示。
        pill: () => (MOCK_DEBTS.length > 0 ? String(MOCK_DEBTS.length) : null),
      },
    ],
  },
  {
    // 知識負債（理解する → 返済する）。input=学習 / output=クイズ を 1 セクションに統合（issue 051）。
    id: "knowledge",
    label: m.nav_section_knowledge,
    items: [
      {
        // クイズ（実測）と学習（返済）はループの両輪。1 メニュー = タブ統合ハブ（/learning）に集約。
        id: "knowledge-hub",
        label: m.nav_knowledge_hub,
        icon: GraduationCap,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}/learning`,
        comingSoon: true,
        // 受験可能クイズ件数を pill 表示（1 件以上のとき）。
        pill: () => (quiz.availableCount > 0 ? String(quiz.availableCount) : null),
      },
    ],
  },
  {
    id: "reference",
    label: m.nav_section_reference,
    items: [
      {
        id: "repos",
        label: m.nav_repos,
        icon: FolderGit2,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}/repos`,
      },
    ],
  },
  {
    id: "system",
    label: null,
    items: [
      {
        id: "settings",
        label: m.nav_settings,
        icon: Settings,
        route: (c) => `/${c.orgSlug}/${c.projectSlug}/settings`,
        comingSoon: true,
      },
    ],
  },
];

/** 全項目をフラットに（ピン留めの解決などに使う） */
export const allNavItems: NavItem[] = navSections.flatMap((s) => s.items);

/**
 * ルートのアクティブ判定。`exact`（Overview = プロジェクトルート）は完全一致、それ以外は前方一致。
 * 前方一致は境界（次が "/" または終端）で区切り、/foo が /foobar に誤マッチしないようにする。
 */
export function isActiveRoute(route: string, pathname: string, exact = false): boolean {
  if (exact) return pathname === route;
  return pathname === route || pathname.startsWith(`${route}/`);
}
