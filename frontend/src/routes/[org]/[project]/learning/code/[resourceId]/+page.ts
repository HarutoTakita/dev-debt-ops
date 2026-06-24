import { getCodeWalkthrough } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ params, url }) => {
  const walkthrough = await getCodeWalkthrough(params.org, params.project, params.resourceId);
  return {
    orgSlug: params.org,
    projectSlug: params.project,
    resourceId: params.resourceId,
    walkthrough,
    planId: url.searchParams.get("planId"),
  };
};
