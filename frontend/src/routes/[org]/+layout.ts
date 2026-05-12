import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";
import { auth } from "$lib/stores/auth.svelte";
import type { LayoutLoad } from "./$types";

export const load: LayoutLoad = async ({ params }) => {
  if (!auth.isAuthenticated) {
    await auth.init();
  }
  if (!auth.isAuthenticated) {
    throw redirect(307, resolve("/login"));
  }
  return { orgSlug: params.org };
};
