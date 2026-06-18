import Activity from "@lucide/svelte/icons/activity";
import Sparkles from "@lucide/svelte/icons/sparkles";
import Grid3x3 from "@lucide/svelte/icons/grid-3x3";
import HelpCircle from "@lucide/svelte/icons/badge-question-mark";
import Bot from "@lucide/svelte/icons/bot";
import GraduationCap from "@lucide/svelte/icons/graduation-cap";
import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
import Settings from "@lucide/svelte/icons/settings";
import type { Pathname } from "$app/types";
import { galaxy } from "$lib/stores/galaxy-store.svelte";
import * as m from "$lib/paraglide/messages";

// すべての lucide アイコンは同一のコンポーネント型を共有するため、1 つから型を借りる。
export type IconComponent = typeof Activity;

export type NavContext = { orgSlug: string; repoConnected: boolean };

export interface NavItem {
  id: string;
  /** i18n ラベル（Paraglide メッセージ関数）。呼び出し時に現在ロケールで解決される。 */
  label: () => string;
  /** org 相対パス（resolve() に渡せる Pathname） */
  route: (ctx: NavContext) => Pathname;
  icon: IconComponent;
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

// GitLab の panel.rb における add_menu 順 = 表示順 / render? を、Rosetta では宣言的配列で表現する。
// understand 系（理解する / 返済する）を上位に、Repos（コード閲覧）は参照として末尾へ格下げする。
export const navSections: NavSection[] = [
  {
    id: "understand",
    label: m.nav_section_understand,
    items: [
      { id: "overview", label: m.nav_overview, icon: Activity, route: (c) => `/${c.orgSlug}` },
      {
        id: "galaxy",
        label: m.nav_galaxy,
        icon: Sparkles,
        route: (c) => `/${c.orgSlug}/galaxy`,
        // 星域観測済み（モック有効）なら自分の KC% を pill 表示、未観測なら非表示
        pill: () => (galaxy.myKc !== null ? `${galaxy.myKc}%` : null),
      },
      {
        id: "matrix",
        label: m.nav_matrix,
        icon: Grid3x3,
        route: (c) => `/${c.orgSlug}/matrix`,
        pill: () => "8",
      },
      {
        id: "quizzes",
        label: m.nav_quizzes,
        icon: HelpCircle,
        route: (c) => `/${c.orgSlug}/quizzes`,
        comingSoon: true,
      },
      { id: "agents", label: m.nav_agents, icon: Bot, route: (c) => `/${c.orgSlug}/agents`, comingSoon: true },
      {
        id: "learning",
        label: m.nav_learning,
        icon: GraduationCap,
        route: (c) => `/${c.orgSlug}/learning`,
        comingSoon: true,
      },
    ],
  },
  {
    id: "reference",
    label: m.nav_section_reference,
    items: [
      {
        // Repos は実装済み唯一の機能。リポジトリ接続の RepoPicker 自体が /repos に在るため、
        // 常に到達可能にする（enabled でゲートすると接続導線が辿れなくなる）。
        // enabled ゲート機構は NavItem 型 / nav-item.svelte に残し、将来のリポジトリスコープ項目で活用する。
        id: "repos",
        label: m.nav_repos,
        icon: FolderGit2,
        route: (c) => `/${c.orgSlug}/repos`,
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
        route: (c) => `/${c.orgSlug}/settings`,
        comingSoon: true,
      },
    ],
  },
];

/** 全項目をフラットに（ピン留めの解決などに使う） */
export const allNavItems: NavItem[] = navSections.flatMap((s) => s.items);

/**
 * ルートのアクティブ判定。Overview（/[org]）は完全一致、それ以外は前方一致。
 * 前方一致は境界（次が "/" または終端）で区切り、/foo が /foobar に誤マッチしないようにする。
 */
export function isActiveRoute(route: string, pathname: string): boolean {
  if (route.split("/").length === 2) return pathname === route;
  return pathname === route || pathname.startsWith(`${route}/`);
}
