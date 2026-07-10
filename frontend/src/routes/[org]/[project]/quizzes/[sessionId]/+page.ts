import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { getQuizSession } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ params }) => {
  const session = await getQuizSession(params.org, params.project, params.sessionId);
  // 採点中 / 採点済みのセッションは回答をロック（サーバは回答 PATCH を 409 で拒否）。回答画面に入っても
  // 保存が全て失敗し「未回答」に見えてしまうため、結果ページへ誘導する（再受験は結果ページの再テストから）。
  if (session.status === "grading" || session.status === "completed") {
    redirect(307, resolve(`/${params.org}/${params.project}/quizzes/${params.sessionId}/result`));
  }
  return { orgSlug: params.org, projectSlug: params.project, session };
};
