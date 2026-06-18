<script lang="ts">
  import { resolve } from "$app/paths";
  import ConstructiveResult from "$lib/components/quiz/constructive-result.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  // 学習プランへ。クイズ結果由来であることを ?from=quiz&attemptId=... で仮配線（§5.4 遷移）。
  const learningHref = $derived(
    `${resolve(`/${data.orgSlug}/learning`)}?from=quiz&attemptId=${data.result.session_id}`,
  );
</script>

<svelte:head>
  <title>{m.quiz_result_title()} · Rosetta</title>
</svelte:head>

<ConstructiveResult result={data.result} {learningHref} />
