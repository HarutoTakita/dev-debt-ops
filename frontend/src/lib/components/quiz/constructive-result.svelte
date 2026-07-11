<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import X from "@lucide/svelte/icons/x";
  import Flag from "@lucide/svelte/icons/flag";
  import Sprout from "@lucide/svelte/icons/sprout";
  import { untrack } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { SvelteSet } from "svelte/reactivity";
  import { createRetest, setQuestionFlag } from "$lib/api/client";
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

  // 設問フラグ（#6）: サーバ初期値で seed。フィルタ再テストの対象になる。楽観更新 + 失敗時ロールバック。
  const flagged = new SvelteSet<string>(
    untrack(() => result.review.filter((r) => r.flagged).map((r) => r.question_id)),
  );
  let retesting = $state(false);
  let retestError = $state<string | null>(null);

  async function toggleFlag(questionId: string) {
    const next = !flagged.has(questionId);
    if (next) flagged.add(questionId);
    else flagged.delete(questionId);
    try {
      await setQuestionFlag(orgSlug, projectSlug, result.session_id, questionId, next);
    } catch {
      if (next) flagged.delete(questionId);
      else flagged.add(questionId);
    }
  }

  // フィルタ再テスト（#6）: 対象設問だけの新セッションを作り、そのクイズへ遷移する。
  async function startRetest(mode: "flagged" | "wrong") {
    if (retesting) return;
    retesting = true;
    retestError = null;
    try {
      const { session_id } = await createRetest(orgSlug, projectSlug, result.session_id, mode);
      await goto(resolve(`/${orgSlug}/${projectSlug}/quizzes/${session_id}`));
    } catch {
      retestError = m.quiz_retest_failed();
      retesting = false;
    }
  }
</script>

<div class="mx-auto max-w-3xl space-y-5 p-4">
  <div class="rounded-lg border bg-card p-6 text-center">
    <h1 class="font-display text-xl font-semibold">{m.quiz_result_title()}</h1>
    <div class="mt-4">
      <KcMeter before={result.kc_before} after={result.kc_after} />
    </div>
  </div>

  <div class="grid gap-4 sm:grid-cols-2 sm:items-start">
    <div class="rounded-lg border bg-card p-4">
      <div class="flex items-center gap-1.5 text-sm font-medium text-success">
        <Check class="size-4" />
        {m.quiz_result_understood()}
      </div>
      <!-- 他の一覧ブロックと同じ rounded-md のリスト項目。長い設問文でもはみ出さず折り返す。 -->
      <ul class="mt-2 space-y-1.5">
        {#each result.understood as c (c.id)}
          <li class="rounded-md border bg-card px-2.5 py-1.5 text-sm break-words">{c.label}</li>
        {/each}
      </ul>
    </div>
    <div class="rounded-lg border bg-card p-4">
      <div class="flex items-center gap-1.5 text-sm font-medium text-debt-code">
        <Sprout class="size-4" />
        {m.quiz_result_gap()}
      </div>
      <ul class="mt-2 space-y-1.5">
        {#each result.gap_concepts as c (c.id)}
          <li>
            <a
              href={galaxyHref}
              title={m.gap_concept_learn({ concept: c.label })}
              aria-label={m.gap_concept_learn({ concept: c.label })}
              class="block rounded-md border bg-card px-2.5 py-1.5 text-sm break-words text-foreground transition-colors hover:bg-accent/40"
            >
              {c.label}
            </a>
          </li>
        {/each}
      </ul>
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
              <button
                type="button"
                onclick={() => toggleFlag(r.question_id)}
                aria-pressed={flagged.has(r.question_id)}
                title={flagged.has(r.question_id) ? m.quiz_flag_remove() : m.quiz_flag_add()}
                class={cn(
                  "shrink-0 rounded p-1 hover:bg-accent/40",
                  flagged.has(r.question_id) ? "text-debt-knowledge" : "text-muted-foreground",
                )}
              >
                <Flag class="size-4" fill={flagged.has(r.question_id) ? "currentColor" : "none"} />
              </button>
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

  {#if flagged.size > 0 || wrongCount > 0}
    <!-- フィルタ再テスト（#6）: フラグした問題だけ / 全回間違えた問題だけ。 -->
    <div class="flex flex-wrap items-center justify-center gap-2">
      {#if flagged.size > 0}
        <Button variant="outline" size="sm" disabled={retesting} onclick={() => startRetest("flagged")}>
          <Flag class="size-4" />
          {m.quiz_retest_flagged()} ({flagged.size})
        </Button>
      {/if}
      {#if wrongCount > 0}
        <Button variant="outline" size="sm" disabled={retesting} onclick={() => startRetest("wrong")}>
          {m.quiz_retest_wrong()}
        </Button>
      {/if}
    </div>
    {#if retestError}
      <p class="text-center text-xs text-destructive">{retestError}</p>
    {/if}
  {/if}

  <div class="text-center">
    <Button href={backHref}>{m.quiz_result_cta()}</Button>
  </div>
</div>
