<script lang="ts">
  import { page } from "$app/state";
  import { Button } from "$lib/components/ui/button";
  import ComingSoonPlaceholder from "$lib/components/quiz/coming-soon-placeholder.svelte";
  import QuizList from "$lib/components/quiz/quiz-list.svelte";
  import { quiz } from "$lib/stores/quiz-store.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
</script>

<svelte:head>
  <title>{m.nav_quizzes()} · Rosetta</title>
</svelte:head>

{#if quiz.availableCount === 0}
  <ComingSoonPlaceholder eyebrow="Re:Pay" title={m.quiz_coming_title()} description={m.quiz_coming_desc()}>
    {#snippet action()}
      <Button onclick={() => quiz.loadAvailable(orgSlug)}>{m.quiz_coming_demo()}</Button>
    {/snippet}
  </ComingSoonPlaceholder>
{:else}
  <div class="mx-auto max-w-2xl space-y-4 p-4">
    <div class="flex items-baseline justify-between gap-2">
      <h1 class="font-display text-xl font-semibold">{m.nav_quizzes()}</h1>
      <span class="text-xs text-muted-foreground">{m.quiz_list_subtitle()}</span>
    </div>
    <QuizList quizzes={quiz.quizzes} {orgSlug} {projectSlug} />
  </div>
{/if}
