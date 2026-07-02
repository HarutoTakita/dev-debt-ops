import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { auth } from "$lib/stores/auth.svelte";
import type { PageLoad } from "./$types";

export const ssr = false;

// アカウント画面ガード: ログイン済みなら誰でも閲覧可（管理者に限らない）。未ログインはログインへ。
export const load: PageLoad = async () => {
  if (!auth.isAuthenticated) await auth.init();
  if (!auth.isAuthenticated) throw redirect(307, resolve("/login"));
  return {};
};
