import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import type { PageLoad } from "./$types";

export const ssr = false;

// 素の /settings は Members へリダイレクト（当面 Settings 配下は Members のみ）。
export const load: PageLoad = ({ params }) => {
  throw redirect(307, resolve(`/${params.org}/settings/members`));
};
