<script lang="ts">
  import { resolve } from "$app/paths";
  import ConstructiveResult from "$lib/components/quiz/constructive-result.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  const learningHref = $derived(resolve(`/${data.orgSlug}/learning`));
</script>

<svelte:head>
  <title>{m.quiz_result_title()} · Rosetta</title>
</svelte:head>

<ConstructiveResult result={data.result} {learningHref} />
