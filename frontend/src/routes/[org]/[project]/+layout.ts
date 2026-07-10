import { error, redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { getProject, SessionExpiredError } from "$lib/api/client";
import type { LayoutLoad } from "./$types";

export const load: LayoutLoad = async ({ params }) => {
  let project;
  try {
    project = await getProject(params.org, params.project);
  } catch (e) {
    // セッション切れは「読み込み失敗」エラー画面ではなくログイン画面へ（再ログインを促す）。
    if (e instanceof SessionExpiredError) {
      throw redirect(307, resolve("/login"));
    }
    throw e;
  }
  if (!project) {
    throw error(404, "プロジェクトが見つかりません");
  }
  return { orgSlug: params.org, project };
};
