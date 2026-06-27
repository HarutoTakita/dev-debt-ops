import { getJob, getQuizResult, submitQuiz } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// 採点は非同期（issue 034）: submit で 202 → getJob ポーリング → getQuizResult で結果取得。
// 冪等化（不具合修正）: 結果ページは再表示/リロードで load が再実行されうる。提出済みのセッションでは
// submitQuiz が null（409）を返すので再提出せず、採点完了まで結果取得をポーリングする（500 を防ぐ）。
export const load: PageLoad = async ({ params }) => {
  const { org, project, sessionId } = params;

  const job = await submitQuiz(org, project, sessionId);
  if (job) {
    // 新規提出時のみ採点ジョブの完了を待つ。
    for (let i = 0; i < 60; i++) {
      const j = await getJob(job.job_id);
      if (j.status === "COMPLETED") break;
      if (j.status === "FAILED") throw new Error("採点に失敗しました");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  // 採点完了まで結果取得をポーリング（採点中は 404 → null）。
  let result = await getQuizResult(org, project, sessionId);
  for (let i = 0; i < 30 && result === null; i++) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    result = await getQuizResult(org, project, sessionId);
  }
  if (result === null) throw new Error("採点結果の取得に失敗しました");

  return { orgSlug: org, projectSlug: project, result };
};
