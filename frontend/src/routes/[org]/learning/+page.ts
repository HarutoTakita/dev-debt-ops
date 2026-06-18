import { mockLearningPlan } from "$lib/mocks/learning-plan";
import type { PageLoad } from "./$types";

export const ssr = false;

// 実データ取得・Vector Search は後続 issue。現状はモックプランを返す。
// クイズ結果からの遷移は ?from=quiz&attemptId=... を仮配線として受ける。
export const load: PageLoad = ({ params, url }) => {
  return {
    orgSlug: params.org,
    plan: mockLearningPlan,
    from: url.searchParams.get("from"),
  };
};
