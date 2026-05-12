<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head><title>{page.status}</title></svelte:head>

<main class="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 p-6 text-center">
  <h1 class="font-display text-3xl font-medium">{page.status}</h1>
  <p class="text-sm text-gray-500">{page.error?.message ?? m.error_page_title()}</p>
  <a href={resolve("/")} class="mt-4 text-sm underline">{m.error_page_go_home()}</a>
</main>
