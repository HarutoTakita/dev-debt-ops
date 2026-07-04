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
  /** route に付与するクエリ文字列（例: `?path=src/…` でファイルを事前選択）。route と併用。 */
  search?: (ctx: { orgSlug: string; projectSlug: string }) => string;
  /** 指定時、表示前にこの data-tour 要素をクリックして target を出す（タブ切替・詳細画面への遷移など）。 */
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
    id: "settings",
    target: "nav-settings",
    title: m.tour_settings_title,
    body: m.tour_settings_body,
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
      id: "galaxy-filter",
      target: "galaxy-filter",
      reveal: "galaxy-tab-map",
      title: m.tour_gx_filter_title,
      body: m.tour_gx_filter_body,
      placement: "bottom",
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
      // 関連ファイルの強調表示。reveal で最多隣接ノードをホバー中として強調し、グラフ表示部分をハイライト。
      id: "galaxy-highlight",
      target: "galaxy-map",
      reveal: "galaxy-hover-demo",
      title: m.tour_gx_highlight_title,
      body: m.tour_gx_highlight_body,
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
      // 機能一覧（/learning）。各学習プランの状態と理解度。
      id: "knowledge-units",
      target: "units-list",
      title: m.tour_kn_units_title,
      body: m.tour_kn_units_body,
      placement: "top",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/learning`,
    },
    {
      // 学習を開く（一覧上のリンク）。
      id: "knowledge-learn",
      target: "unit-learn",
      title: m.tour_kn_learn_title,
      body: m.tour_kn_learn_body,
      placement: "bottom",
    },
    {
      // 「このコードを理解する」= リポジトリ特有の機能の学習プラン。reveal で学習プランを開く。
      id: "knowledge-plan-code",
      target: "plan-code",
      reveal: "unit-learn",
      title: m.tour_kn_plan_code_title,
      body: m.tour_kn_plan_code_body,
      placement: "right",
    },
    {
      // 「技術スタックを学ぶ」= 関連技術の公式ドキュメント/チュートリアル（先頭 1 件をハイライト）。
      id: "knowledge-plan-stack",
      target: "plan-stack-first",
      title: m.tour_kn_plan_stack_title,
      body: m.tour_kn_plan_stack_body,
      placement: "left",
    },
    {
      // 進捗確認: チェック済みを集計した全体進捗（進捗バー）。
      id: "knowledge-progress",
      target: "plan-progress",
      title: m.tour_kn_plan_title,
      body: m.tour_kn_plan_body,
      placement: "bottom",
    },
    {
      // 理解度テストの実施。一覧へ戻り「理解度を確認する」でクイズへ。左コード＋右解答をまとめてハイライト。
      id: "knowledge-quiz",
      target: "quiz-body",
      reveal: "unit-confirm",
      title: m.tour_kn_quiz_title,
      body: m.tour_kn_quiz_body,
      placement: "top",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/learning`,
    },
    {
      // 不安な問題へのフラグ付け。reveal でフラグを有効化した状態でハイライト。
      id: "knowledge-flag",
      target: "quiz-flag",
      reveal: "quiz-flag",
      title: m.tour_kn_flag_title,
      body: m.tour_kn_flag_body,
      placement: "bottom",
    },
    {
      // テスト結果確認（中央説明）。採点後の結果画面の説明。
      id: "knowledge-result",
      title: m.tour_kn_result_title,
      body: m.tour_kn_result_body,
      placement: "bottom",
    },
    {
      // 再テスト（中央説明）。フラグ/誤答に絞った再受験。
      id: "knowledge-retest",
      title: m.tour_kn_retest_title,
      body: m.tour_kn_retest_body,
      placement: "bottom",
    },
  ],
  // 「コード品質マップ」（nav id=matrix, ラベル=コード品質マップ, ルート=/repos）の詳細ガイド。
  // ファイルツリー＋ファイル閲覧＋指摘箇所。指摘のあるファイルを事前選択して閲覧欄を空にしない。
  matrix: [
    {
      // 概要はページ上部の説明文に載せるため、ガイドはファイルツリーから開始する。
      // 当ページへ遷移し、指摘のあるファイルを事前選択して閲覧欄を空にしない。
      id: "repos-tree",
      target: "repos-tree",
      title: m.tour_rp_tree_title,
      body: m.tour_rp_tree_body,
      placement: "right",
      route: (c) => `/${c.orgSlug}/${c.projectSlug}/repos`,
      search: () => "?path=src/checkout/payment.py",
    },
    {
      id: "repos-viewer",
      target: "repos-viewer",
      title: m.tour_rp_viewer_title,
      body: m.tour_rp_viewer_body,
      placement: "left",
    },
    {
      // 指摘箇所。一番目の指摘を reveal（クリック）してソースをハイライトした状態で説明する。
      id: "repos-debts",
      target: "repos-debts",
      reveal: "repos-debt-first",
      title: m.tour_rp_debts_title,
      body: m.tour_rp_debts_body,
      placement: "top",
    },
  ],
  // 「コード改善」（nav id=repos, ラベル=コード改善, ルート=/matrix）の詳細ガイド。
  // 改善対象リスト → 先頭項目をクリックして詳細（改善箇所ハイライト・AI に頼む/人に頼む）まで案内。
  repos: [
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
      target: "matrix-first-row",
      title: m.tour_mx_list_title,
      body: m.tour_mx_list_body,
      placement: "bottom",
    },
    {
      id: "matrix-improve",
      target: "debt-improve",
      reveal: "matrix-first-row",
      title: m.tour_mx_improve_title,
      body: m.tour_mx_improve_body,
      placement: "left",
    },
    {
      id: "matrix-ai",
      target: "debt-ai",
      title: m.tour_mx_ai_title,
      body: m.tour_mx_ai_body,
      placement: "left",
    },
    {
      id: "matrix-human",
      target: "debt-human",
      title: m.tour_mx_human_title,
      body: m.tour_mx_human_body,
      placement: "left",
    },
  ],
};
