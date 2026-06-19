<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Logo from "$lib/components/logo.svelte";
  import * as m from "$lib/paraglide/messages";

  // org コンテキストがあれば一覧（/[org]）へ、無ければホームへ戻す。
  const orgSlug = $derived(page.params.org ?? "");
</script>

<svelte:head><title>{page.status}</title></svelte:head>

<main class="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 p-6 text-center">
  <Logo class="size-10 text-debt-knowledge" />
  <h1 class="font-display text-3xl font-medium">{page.status}</h1>
  <p class="text-sm text-gray-500">{page.error?.message ?? m.error_page_title()}</p>
  {#if orgSlug}
    <a href={resolve(`/${orgSlug}`)} class="mt-4 text-sm underline">{m.error_page_back_projects()}</a>
  {:else}
    <a href={resolve("/")} class="mt-4 text-sm underline">{m.error_page_go_home()}</a>
  {/if}
</main>
