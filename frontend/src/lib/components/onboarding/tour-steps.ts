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
// 当該ページへ遷移し、中央に詳しい説明を出す（target 無し）。MVP は 1 ステップ／ページ。
export const pageTours: Record<string, TourStep[]> = {
  overview: [
    {
      id: "overview-detail",
      title: m.tour_overview_title,
      body: m.tour_overview_detail,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}`,
    },
  ],
  galaxy: [
    {
      id: "galaxy-detail",
      title: m.tour_galaxy_title,
      body: m.tour_galaxy_detail,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/galaxy`,
    },
  ],
  "knowledge-hub": [
    {
      id: "knowledge-detail",
      title: m.tour_knowledge_title,
      body: m.tour_knowledge_detail,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/learning`,
    },
  ],
  matrix: [
    {
      id: "matrix-detail",
      title: m.tour_matrix_title,
      body: m.tour_matrix_detail,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/matrix`,
    },
  ],
  repos: [
    {
      id: "repos-detail",
      title: m.tour_repos_title,
      body: m.tour_repos_detail,
      placement: "bottom",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/repos`,
    },
  ],
};
