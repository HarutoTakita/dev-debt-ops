<script lang="ts">
  import X from "@lucide/svelte/icons/x";
  import Check from "@lucide/svelte/icons/check";
  import { scale } from "svelte/transition";
  import type { QuizSession } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import { quiz } from "$lib/stores/quiz-store.svelte";
  import CodeSnippetPanel from "./code-snippet-panel.svelte";
  import AnswerInput from "./answer-input.svelte";
  import * as m from "$lib/paraglide/messages";

  // 集中モードのシェル。進捗インジケータ + 途中保存ステータス + コード/解答の 2 ペイン。
  type Props = { session: QuizSession; onexit: () => void; onsubmit: () => void };
  const { session, onexit, onsubmit }: Props = $props();

  let index = $state(0);
  const total = $derived(session.questions.length);
  const q = $derived(session.questions[index]);
  const value = $derived(quiz.draftAnswers[q.id]?.value ?? "");
  const isLast = $derived(index === total - 1);

  function onanswer(v: string) {
    quiz.saveDraft({ question_id: q.id, value: v, saved_at: new Date().toISOString() });
  }

  function savedTime(): string {
    return quiz.savedAt
      ? new Date(quiz.savedAt).toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" })
      : "";
  }
</script>

<div class="flex h-full flex-col">
  <!-- ヘッダ: 進捗 + 途中保存ステータス + 中断 -->
  <div class="flex items-center justify-between gap-2 border-b px-4 py-2 text-sm">
    <span class="font-medium">{m.quiz_focus_progress({ current: index + 1, total })}</span>
    <span class="text-xs text-muted-foreground">
      {#if quiz.saveStatus === "saving"}
        ◌ {m.quiz_save_saving()}
      {:else if quiz.saveStatus === "saved"}
        <!-- 保存確定ごとにチェックを一度ポップさせる（KcMeter と同じ success トーン） -->
        {#key quiz.savedAt}
          <span class="inline-flex items-center gap-1 text-success" in:scale={{ duration: 200, start: 0.7 }}>
            <Check class="size-3.5" />
            {m.quiz_save_saved({ time: savedTime() })}
          </span>
        {/key}
      {/if}
    </span>
    <button onclick={onexit} class="text-muted-foreground hover:text-foreground" aria-label={m.quiz_focus_abort()}>
      <X class="size-4" />
    </button>
  </div>

  <!-- 本体: 左コード / 右解答。モバイルは縦積み＋ページスクロール（各ペインが潰れないよう高さを確保）、
       lg 以上で左右 2 ペイン＋各ペイン内スクロール。 -->
  <div class="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 lg:grid-cols-2 lg:overflow-hidden">
    <div class="min-h-0 max-lg:h-72">
      {#if q.code_snippet}
        <CodeSnippetPanel snippet={q.code_snippet} />
      {:else}
        <div class="flex h-full items-center justify-center rounded-lg border bg-card text-sm text-muted-foreground">
          {m.quiz_focus_no_snippet()}
        </div>
      {/if}
    </div>
    <div class="flex min-h-0 flex-col gap-3 lg:overflow-auto">
      <span class="w-fit rounded bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums">{q.difficulty}</span>
      <p class="text-sm font-medium">{q.prompt}</p>
      <AnswerInput question={q} {value} {onanswer} />
    </div>
  </div>

  <!-- フッタ: 前へ / 次へ・提出 -->
  <div class="flex items-center justify-between gap-2 border-t px-4 py-2">
    <Button variant="outline" size="sm" disabled={index === 0} onclick={() => (index -= 1)}>
      ← {m.quiz_focus_prev()}
    </Button>
    {#if isLast}
      <Button size="sm" onclick={onsubmit}>{m.quiz_focus_submit()}</Button>
    {:else}
      <Button size="sm" onclick={() => (index += 1)}>{m.quiz_focus_next()} →</Button>
    {/if}
  </div>
</div>
