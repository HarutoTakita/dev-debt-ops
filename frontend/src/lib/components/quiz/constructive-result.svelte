<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import X from "@lucide/svelte/icons/x";
  import Sprout from "@lucide/svelte/icons/sprout";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import type { QuizResult } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { cn } from "$lib/utils";
  import KcMeter from "./kc-meter.svelte";
  import * as m from "$lib/paraglide/messages";

  // 「正解/不正解」を出さない建設的フレーミング。理解していたこと / 学ぶ余地 + 理解度カウントアップ。
  type Props = { result: QuizResult; backHref: string };
  const { result, backHref }: Props = $props();

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const galaxyHref = $derived(resolve(`/${orgSlug}/${projectSlug}/galaxy`));

  // 誤答チェック（#4）: 誤答を先頭に並べ、各設問の自分の回答 vs 正答を確認できる。
  const review = $derived([...result.review].sort((a, b) => Number(a.is_correct) - Number(b.is_correct)));
  const wrongCount = $derived(result.review.filter((r) => !r.is_correct).length);
</script>

<div class="mx-auto max-w-2xl space-y-5 p-4">
  <div class="rounded-lg border bg-card p-6 text-center">
    <h1 class="font-display text-xl font-semibold">{m.quiz_result_title()}</h1>
    <div class="mt-4">
      <KcMeter before={result.kc_before} after={result.kc_after} />
    </div>
  </div>

  <div class="grid gap-4 sm:grid-cols-2">
    <div class="rounded-lg border bg-card p-4">
      <div class="flex items-center gap-1.5 text-sm font-medium text-success">
        <Check class="size-4" />
        {m.quiz_result_understood()}
      </div>
      <ul class="mt-2 space-y-1 text-sm text-muted-foreground">
        {#each result.understood as c (c.id)}<li>・{c.label}</li>{/each}
      </ul>
    </div>
    <div class="rounded-lg border bg-card p-4">
      <div class="flex items-center gap-1.5 text-sm font-medium text-debt-code">
        <Sprout class="size-4" />
        {m.quiz_result_gap()}
      </div>
      <div class="mt-2 flex flex-wrap gap-1.5">
        {#each result.gap_concepts as c (c.id)}
          <a
            href={galaxyHref}
            title={m.gap_concept_learn({ concept: c.label })}
            aria-label={m.gap_concept_learn({ concept: c.label })}
            class="inline-flex items-center rounded-full border bg-card px-2 py-0.5 text-sm font-medium text-foreground transition-colors hover:bg-accent/40"
          >
            {c.label}
          </a>
        {/each}
      </div>
    </div>
  </div>

  {#if review.length > 0}
    <!-- 誤答チェック（#4）: 全設問の正誤 + 誤答は自分の回答/正答を表示。 -->
    <div class="rounded-lg border bg-card p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium">{m.quiz_review_title()}</h2>
        <span class="text-xs text-muted-foreground">
          {wrongCount === 0 ? m.quiz_review_all_correct() : m.quiz_review_wrong_count({ count: wrongCount })}
        </span>
      </div>
      <ul class="mt-3 space-y-2">
        {#each review as r (r.question_id)}
          <li
            class={cn(
              "rounded-md border p-2.5",
              r.is_correct ? "border-border" : "border-destructive/40 bg-destructive/5",
            )}
          >
            <div class="flex items-start gap-2">
              {#if r.is_correct}
                <Check class="mt-0.5 size-4 shrink-0 text-success" />
              {:else}
                <X class="mt-0.5 size-4 shrink-0 text-destructive" />
              {/if}
              <p class="min-w-0 flex-1 text-sm">{r.prompt}</p>
            </div>
            {#if !r.is_correct}
              <dl class="mt-2 space-y-0.5 pl-6 text-xs">
                <div class="flex gap-2">
                  <dt class="shrink-0 text-muted-foreground">{m.quiz_review_your()}</dt>
                  <dd class="text-destructive">{r.your_answer || m.quiz_review_unanswered()}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="shrink-0 text-muted-foreground">{m.quiz_review_correct()}</dt>
                  <dd class="font-medium text-success">{r.correct_answer}</dd>
                </div>
              </dl>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <div class="text-center">
    <Button href={backHref}>{m.quiz_result_cta()}</Button>
  </div>
</div>
