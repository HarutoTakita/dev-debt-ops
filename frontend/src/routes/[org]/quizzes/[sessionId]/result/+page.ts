import { submitQuiz } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ params }) => {
  // 採点本体は未実装。submitQuiz はモック結果（KC 0.23 → 0.47）を返す。
  const result = await submitQuiz(params.sessionId);
  return { orgSlug: params.org, result };
};
