import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { auth } from "$lib/stores/auth.svelte";
import type { PageLoad } from "./$types";

export const ssr = false;

// 管理画面ガード（issue 300）: 未ログインはログインへ、管理者(superuser)でなければトップへリダイレクト。
// ロールは .env `ADMIN_EMAILS` 由来（ログイン時に整合）で、GitHub SSO ユーザーは既定で一般ユーザー。
export const load: PageLoad = async () => {
  if (!auth.isAuthenticated) await auth.init();
  if (!auth.isAuthenticated) throw redirect(307, resolve("/login"));
  if (!auth.isAdmin) throw redirect(307, resolve("/"));
  return {};
};
