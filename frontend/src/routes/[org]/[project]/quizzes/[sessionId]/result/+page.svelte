<script lang="ts">
  import { resolve } from "$app/paths";
  import ConstructiveResult from "$lib/components/quiz/constructive-result.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  // 結果ページからは「クイズと学習」の一覧（単元一覧）へ戻る。
  const backHref = $derived(resolve(`/${data.orgSlug}/${data.projectSlug}/learning`));
</script>

<svelte:head>
  <title>{m.quiz_result_title()} · DevDebtOps</title>
</svelte:head>

<ConstructiveResult result={data.result} {backHref} />
