import { error } from "@sveltejs/kit";
import { getProject } from "$lib/api/client";
import type { LayoutLoad } from "./$types";

export const load: LayoutLoad = async ({ params }) => {
  const project = await getProject(params.org, params.project);
  if (!project) {
    throw error(404, "プロジェクトが見つかりません");
  }
  return { orgSlug: params.org, project };
};
