<script lang="ts">
  import { page } from "$app/state";

  const orgSlug = $derived(page.params.org);
</script>

<svelte:head>
  <title>Dashboard · Rosetta</title>
</svelte:head>

<div class="p-8">
  <h1 class="text-2xl font-bold">Dashboard</h1>
  <p class="text-muted-foreground mt-1">{orgSlug}</p>
</div>
