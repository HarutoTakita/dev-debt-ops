<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head>
  <title>{m.nav_settings()} · Rosetta</title>
</svelte:head>

<ComingSoonPlaceholder feature={m.nav_settings()} description={m.coming_settings_desc()} />
