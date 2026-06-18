<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head>
  <title>{m.nav_agents()} · Rosetta</title>
</svelte:head>

<ComingSoonPlaceholder feature={m.nav_agents()} description={m.coming_agents_desc()} />
