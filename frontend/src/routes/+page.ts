import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { auth } from "$lib/stores/auth.svelte";
import type { PageLoad } from "./$types";

export const load: PageLoad = async () => {
  await auth.init();
  if (auth.isAuthenticated) {
    throw redirect(307, resolve("/login/callback"));
  }
  throw redirect(307, resolve("/login"));
};
