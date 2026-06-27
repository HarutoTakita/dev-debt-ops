<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import FocusMode from "$lib/components/quiz/focus-mode.svelte";
  import { quiz } from "$lib/stores/quiz-store.svelte";

  let { data } = $props();

  // セッション入室時に途中保存の文脈を確定（ドラフトもリセット。セッション切替時も再実行）。
  $effect(() => {
    quiz.setContext(data.orgSlug, data.projectSlug, data.session.id);
  });

  function exit() {
    goto(resolve(`/${data.orgSlug}/${data.projectSlug}/quizzes`));
  }
  function submit() {
    goto(resolve(`/${data.orgSlug}/${data.projectSlug}/quizzes/${data.session.id}/result`));
  }
</script>

<svelte:head>
  <title>{data.session.file.path} · DevDebtOps</title>
</svelte:head>

<div class="h-full">
  {#key data.session.id}
    <FocusMode session={data.session} onexit={exit} onsubmit={submit} />
  {/key}
</div>
