import { generatePlan, getJob, getLearningPlan } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// 実 API（issue 035）: planId があれば取得。?from=quiz&attemptId=... 経由なら生成 enqueue → ポーリング → 取得。
export const load: PageLoad = async ({ params, url }) => {
  const { org, project } = params;
  const from = url.searchParams.get("from");
  let planId = url.searchParams.get("planId");
  const attemptId = url.searchParams.get("attemptId");

  if (!planId && attemptId) {
    const { job_id, plan_id } = await generatePlan(org, project, { attemptId });
    planId = plan_id;
    for (let i = 0; i < 60; i++) {
      const job = await getJob(job_id);
      if (job.status === "COMPLETED") break;
      if (job.status === "FAILED") throw new Error("学習プランの生成に失敗しました");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  const plan = planId ? await getLearningPlan(org, project, planId) : null;
  return { orgSlug: org, projectSlug: project, plan, from };
};
