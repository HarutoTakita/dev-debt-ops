<script lang="ts">
  import ComingSoonPlaceholder from "$lib/components/common/coming-soon-placeholder.svelte";
  import PlanProgress from "$lib/components/learning/plan-progress.svelte";
  import ResourceList from "$lib/components/learning/resource-list.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  // 機能本体は未実装。既定は Coming Soon、開発用リンクでモックレイアウトをプレビュー。
  let preview = $state(false);
</script>

<svelte:head>
  <title>{m.nav_learning()} · Rosetta</title>
</svelte:head>

{#if !preview}
  <div class="flex h-full flex-col">
    <div class="flex-1">
      <ComingSoonPlaceholder title={m.learning_coming_title()} description={m.learning_coming_body()} />
    </div>
    <div class="shrink-0 pb-8 text-center">
      <button
        type="button"
        onclick={() => (preview = true)}
        class="text-xs text-muted-foreground underline hover:text-foreground"
      >
        {m.learning_preview()}
      </button>
    </div>
  </div>
{:else}
  <div class="mx-auto max-w-2xl space-y-4 p-4">
    <div>
      <h1 class="font-display text-xl font-semibold">{m.nav_learning()}</h1>
      {#if data.from === "quiz"}
        <p class="mt-0.5 text-xs text-debt-knowledge">{m.learning_from_quiz()}</p>
      {/if}
      <p class="mt-1 text-xs text-muted-foreground">{m.learning_gap()}: {data.plan.gap_concepts.join(" / ")}</p>
    </div>
    <PlanProgress plan={data.plan} />
    <ResourceList steps={data.plan.steps} />
  </div>
{/if}
