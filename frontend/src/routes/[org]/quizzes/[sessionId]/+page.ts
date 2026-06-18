import { getQuizSession } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ params }) => {
  const session = await getQuizSession(params.sessionId);
  return { orgSlug: params.org, session };
};
