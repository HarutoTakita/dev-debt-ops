import { getMyMembership } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// 権限ガードの初期値として自分のロールを取得する。
export const load: PageLoad = async ({ params }) => {
  const me = await getMyMembership(params.org);
  return { orgSlug: params.org, myRole: me?.role ?? null };
};
