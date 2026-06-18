<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import FocusMode from "$lib/components/quiz/focus-mode.svelte";
  import { quiz } from "$lib/stores/quiz-store.svelte";

  let { data } = $props();

  // セッション入室時にドラフトをリセット（セッション切替時も再実行）。
  $effect(() => {
    void data.session.id;
    quiz.reset();
  });

  function exit() {
    goto(resolve(`/${data.orgSlug}/quizzes`));
  }
  function submit() {
    goto(resolve(`/${data.orgSlug}/quizzes/${data.session.id}/result`));
  }
</script>

<svelte:head>
  <title>{data.session.file.path} · Rosetta</title>
</svelte:head>

<div class="h-full">
  {#key data.session.id}
    <FocusMode session={data.session} onexit={exit} onsubmit={submit} />
  {/key}
</div>
