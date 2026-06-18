<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head>
  <title>{m.nav_learning()} · Rosetta</title>
</svelte:head>

<ComingSoonPlaceholder feature={m.nav_learning()} description={m.coming_learning_desc()} />
