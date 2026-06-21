import { redirect } from "@sveltejs/kit";
import type { PageLoad } from "./$types";

export const ssr = false;

// エージェント独立ビューは廃止し、解析/ループ状況は観測台（ダッシュボード）へ集約（issue 051）。
// 旧ディープリンク（loop_agents.deepLink や debt-meta-panel のリンク等）が切れないよう、
// /[org]/[project]/agents は観測台へ恒久リダイレクトする。
export const load: PageLoad = ({ params }) => {
  redirect(308, `/${params.org}/${params.project}`);
};
