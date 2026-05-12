<script lang="ts">
  import { page } from "$app/state";

  let { children } = $props();

  const orgSlug = $derived(page.params.org);
</script>

<div class="flex min-h-screen flex-col">
  <header class="flex items-center border-b px-4 py-2">
    <span class="font-semibold">{orgSlug}</span>
  </header>
  <main class="flex-1">
    {@render children()}
  </main>
</div>
