// オンボーディングガイドの起動ロジック（issue 066 追補）。手動起動（ヘルプ）と初回作成後の自動起動で共通化する。
// 3 分岐に出し分ける:
//   1) デモモード          → データ準備済みの EC デモ（sample-shop）へ遷移し、通常ガイドを展開する
//   2) 未解析プロジェクト  → 解析パネルだけを案内するガイド（通常ガイドは実データ前提で空だと壊れるため）
//   3) 解析済みプロジェクト → 通常ガイド（PC=サイドバー版 / モバイル=ページ内コンテンツ版）
// エンジン（onboarding-tour.svelte）・各ステップ定義は不変で、ここは「どのステップ列を start するか」だけを担う。

import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import { getAnalysisStatus } from "$lib/api/client";
import { auth } from "$lib/stores/auth.svelte";
import { onboarding } from "$lib/stores/onboarding-store.svelte";
import { project } from "$lib/stores/project-store.svelte";
import {
  analysisOnlySteps,
  DEMO_PROJECT_SLUG,
  isMobileTour,
  mobileTourSteps,
  noProjectSteps,
  tourSteps,
} from "./tour-steps";

/** そのプロジェクトが 1 度でも解析完了しているか（=各画面に案内できるデータがあるか）。
 *  analysis-status に COMPLETED のジョブが 1 つでもあれば解析済みと見なす。
 *  取得できなかった場合は「未解析（false）」に倒す — 通常ガイドで空画面を案内して壊すより、解析導線を出す方が安全。 */
async function isAnalyzed(orgSlug: string, projectSlug: string): Promise<boolean> {
  try {
    const status = await getAnalysisStatus(orgSlug, projectSlug);
    return Object.values(status.jobs).some((j) => j.status === "COMPLETED");
  } catch {
    return false;
  }
}

/** PC=サイドバー版 tourSteps / モバイル=ページ内コンテンツ版 mobileTourSteps を出し分けて開始する。 */
function startNormalTour() {
  onboarding.start(isMobileTour() ? mobileTourSteps : tourSteps);
}

/** ヘルプメニューからの手動起動。呼び出し側はモバイルドロワーを閉じてから呼ぶこと。 */
export async function startGuideFor(orgSlug: string): Promise<void> {
  if (!orgSlug) return;
  // デモ: 他プロジェクト（メタデータのみ）や未選択で開始しても壊れないよう、必ずデータ準備済みの EC デモへ。
  if (auth.isDemo) {
    if (project.current?.slug !== DEMO_PROJECT_SLUG) await goto(resolve(`/${orgSlug}/${DEMO_PROJECT_SLUG}`));
    startNormalTour();
    return;
  }
  // 実ユーザー: プロジェクトが 1 つも無ければ「新規プロジェクト作成」へ誘導。
  const target = project.current ?? project.list[0];
  if (!target) {
    onboarding.start(noProjectSteps);
    return;
  }
  if (project.current?.slug !== target.slug) await goto(resolve(`/${orgSlug}/${target.slug}`));
  // 未解析（データ無し）なら解析のみ案内し、完了後の再起動を促す。
  if (!(await isAnalyzed(orgSlug, target.slug))) {
    onboarding.start(analysisOnlySteps);
    return;
  }
  startNormalTour();
}

/** 初回プロジェクト作成後の自動起動。作成直後は未解析のため解析ガイドを出す（データ生成後の再起動を促す）。 */
export async function autoStartGuideFor(orgSlug: string, projectSlug: string): Promise<void> {
  if (!orgSlug || !projectSlug) return;
  if (auth.isDemo) {
    startNormalTour();
    return;
  }
  if (!(await isAnalyzed(orgSlug, projectSlug))) {
    onboarding.start(analysisOnlySteps);
    return;
  }
  startNormalTour();
}
