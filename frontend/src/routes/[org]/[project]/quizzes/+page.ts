import { redirect } from "@sveltejs/kit";
import type { PageLoad } from "./$types";

export const ssr = false;

// クイズ一覧は統合ハブ（/learning のクイズタブ）へ移設（issue: クイズ+学習の統合）。
// 旧 /quizzes へのリンク・ブックマークを恒久リダイレクトで救済する。
export const load: PageLoad = ({ params }) => {
  redirect(308, `/${params.org}/${params.project}/learning?tab=quiz`);
};
