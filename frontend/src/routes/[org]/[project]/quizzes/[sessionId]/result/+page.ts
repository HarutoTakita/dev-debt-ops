import { getJob, getQuizResult, submitQuiz } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// 採点は非同期（issue 034）: submit で 202 → getJob ポーリング → getQuizResult で結果取得。
export const load: PageLoad = async ({ params }) => {
  const { org, project, sessionId } = params;
  const { job_id } = await submitQuiz(org, project, sessionId);

  for (let i = 0; i < 60; i++) {
    const job = await getJob(job_id);
    if (job.status === "COMPLETED") break;
    if (job.status === "FAILED") throw new Error("採点に失敗しました");
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  const result = await getQuizResult(org, project, sessionId);
  return { orgSlug: org, projectSlug: project, result };
};
