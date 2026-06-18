<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/shell/coming-soon-placeholder.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<svelte:head>
  <title>{m.nav_quizzes()} · Rosetta</title>
</svelte:head>

<ComingSoonPlaceholder feature={m.nav_quizzes()} description={m.coming_quizzes_desc()} />
