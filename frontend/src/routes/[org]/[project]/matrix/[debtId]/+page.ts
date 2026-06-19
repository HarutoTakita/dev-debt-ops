import { getDebt } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ params }) => {
  const debt = await getDebt(params.org, params.project, params.debtId);
  return { orgSlug: params.org, projectSlug: params.project, debt };
};
