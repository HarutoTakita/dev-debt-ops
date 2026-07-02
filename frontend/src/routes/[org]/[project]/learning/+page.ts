import { getLearningPlan } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// 学習プランは「解析」時に機能ごと事前生成済み（issue 298）。閲覧は表示のみ — ?planId があれば取得して表示する
// （単元ハブ knowledge-unit-list が learning_plan_id へリンク）。オンデマンド生成（旧 ?attemptId=）は廃止し、
// Gemini 呼び出しを「解析」と「PR 作成」に限定する。
export const load: PageLoad = async ({ params, url }) => {
  const { org, project } = params;
  const from = url.searchParams.get("from");
  const planId = url.searchParams.get("planId");

  const plan = planId ? await getLearningPlan(org, project, planId) : null;
  return { orgSlug: org, projectSlug: project, plan, from };
};
