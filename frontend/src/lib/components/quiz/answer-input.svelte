<script lang="ts">
  import type { QuizQuestion } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 選択肢 / 自由記述を kind で出し分け、入力ごとに onanswer を呼ぶ（途中保存ドラフト）。
  type Props = { question: QuizQuestion; value: string; onanswer: (value: string) => void };
  const { question, value, onanswer }: Props = $props();
</script>

{#if question.kind === "multiple_choice"}
  <div class="space-y-2">
    {#each question.choices ?? [] as choice (choice.id)}
      <label
        class={cn(
          "flex cursor-pointer items-center gap-2 rounded-md border p-2.5 text-sm transition-colors hover:bg-accent/40",
          value === choice.id && "border-primary bg-accent/40",
        )}
      >
        <input
          type="radio"
          name={question.id}
          value={choice.id}
          checked={value === choice.id}
          onchange={() => onanswer(choice.id)}
          class="accent-primary"
        />
        {choice.label}
      </label>
    {/each}
  </div>
{:else}
  <textarea
    {value}
    oninput={(e) => onanswer(e.currentTarget.value)}
    placeholder={m.quiz_answer_placeholder()}
    rows="6"
    class="w-full rounded-md border p-3 text-sm focus:ring-2 focus:ring-ring focus:outline-none"
  ></textarea>
{/if}
