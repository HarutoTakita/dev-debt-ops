// オンボーディングツアーのステップ定義（issue 066）。
// target は対象要素の data-tour 値。route があれば表示前にそのページへ遷移してからハイライトする。
// 文言は Paraglide メッセージ関数（呼び出し時に現在ロケールで解決）。

import type { Pathname } from "$app/types";
import * as m from "$lib/paraglide/messages";

export type TourPlacement = "right" | "bottom" | "left" | "top";

export type TourStep = {
  id: string;
  /** ハイライト対象の data-tour 値。省略時は中央に説明だけ出す（ページ別ガイドの詳細説明用）。 */
  target?: string;
  title: () => string;
  body: () => string;
  placement: TourPlacement;
  /** 指定時、表示前にこのプロジェクト相対パスへ遷移する。 */
  route?: (ctx: { orgSlug: string; projectSlug: string }) => Pathname;
  /** 指定時、表示前にこの data-tour 要素をクリックして target を出す（タブ切替などの隠れ要素対策）。 */
  reveal?: string;
};

// 順序は左サイドバーの上から（ダッシュボード → 理解度マップ → クイズと学習 → コード品質マップ → コード改善）。
// 続けて、トップバー右上の「解析」ボタンとヘルプ ?。
export const tourSteps: TourStep[] = [
  {
    id: "overview",
    target: "nav-overview",
    title: m.tour_overview_title,
    body: m.tour_overview_body,
    placement: "right",
  },
  {
    id: "galaxy",
    target: "nav-galaxy",
    title: m.tour_galaxy_title,
    body: m.tour_galaxy_body,
    placement: "right",
  },
  {
    id: "knowledge-hub",
    target: "nav-knowledge-hub",
    title: m.tour_knowledge_title,
    body: m.tour_knowledge_body,
    placement: "right",
  },
  {
    id: "matrix",
    target: "nav-matrix",
    title: m.tour_matrix_title,
    body: m.tour_matrix_body,
    placement: "right",
  },
  {
    id: "repos",
    target: "nav-repos",
    title: m.tour_repos_title,
    body: m.tour_repos_body,
    placement: "right",
  },
  {
    // 最重要操作。トップバー右上の「解析」ボタン（常時表示）をハイライト。
    id: "analysis",
    target: "analysis-run",
    title: m.tour_analysis_title,
    body: m.tour_analysis_body,
    placement: "bottom",
  },
  {
    id: "help",
    target: "help",
    title: m.tour_help_title,
    body: m.tour_help_body,
    placement: "right",
  },
];

// 各メニューの「詳細を確認する」で開くページ別ガイド（issue 066）。メイン手順の id をキーにする。
// 先頭ステップで当該ページへ遷移（route）し、各ページの主要 UI 要素を順にハイライトして詳しく説明する。
// タブ等の隠れ要素は reveal（表示前のクリック）で出してから計測する。
export const pageTours: Record<string, TourStep[]> = {
  overview: [
    {
      id: "overview-primary",
      target: "overview-primary",
      title: m.tour_ov_primary_title,
      body: m.tour_ov_primary_body,
      placement: "top",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}`,
    },
    {
      id: "overview-stats",
      target: "overview-stats",
      title: m.tour_ov_stats_title,
      body: m.tour_ov_stats_body,
      placement: "top",
    },
    {
      id: "overview-trend",
      target: "overview-trend",
      title: m.tour_ov_trend_title,
      body: m.tour_ov_trend_body,
      placement: "top",
    },
    {
      id: "overview-priority",
      target: "overview-priority",
      title: m.tour_ov_priority_title,
      body: m.tour_ov_priority_body,
      placement: "top",
    },
  ],
  galaxy: [
    {
      id: "galaxy-views",
      target: "galaxy-views",
      title: m.tour_gx_views_title,
      body: m.tour_gx_views_body,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/galaxy`,
    },
    {
      id: "galaxy-map",
      target: "galaxy-map",
      reveal: "galaxy-tab-map",
      title: m.tour_gx_map_title,
      body: m.tour_gx_map_body,
      placement: "left",
    },
    {
      id: "galaxy-list",
      target: "galaxy-list",
      reveal: "galaxy-tab-list",
      title: m.tour_gx_list_title,
      body: m.tour_gx_list_body,
      placement: "top",
    },
  ],
  "knowledge-hub": [
    {
      id: "knowledge-units",
      target: "units-list",
      title: m.tour_kn_units_title,
      body: m.tour_kn_units_body,
      placement: "top",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/learning`,
    },
    {
      id: "knowledge-learn",
      target: "unit-learn",
      title: m.tour_kn_learn_title,
      body: m.tour_kn_learn_body,
      placement: "bottom",
    },
    {
      id: "knowledge-confirm",
      target: "unit-confirm",
      title: m.tour_kn_confirm_title,
      body: m.tour_kn_confirm_body,
      placement: "bottom",
    },
  ],
  matrix: [
    {
      id: "matrix-search",
      target: "matrix-search",
      title: m.tour_mx_search_title,
      body: m.tour_mx_search_body,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/matrix`,
    },
    {
      id: "matrix-list",
      target: "matrix-list",
      title: m.tour_mx_list_title,
      body: m.tour_mx_list_body,
      placement: "top",
    },
  ],
  repos: [
    {
      id: "repos-tree",
      target: "repos-tree",
      title: m.tour_rp_tree_title,
      body: m.tour_rp_tree_body,
      placement: "right",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/repos`,
    },
    {
      id: "repos-viewer",
      target: "repos-viewer",
      title: m.tour_rp_viewer_title,
      body: m.tour_rp_viewer_body,
      placement: "left",
    },
  ],
};
