<script lang="ts">
  import type { QuizQuestion } from "$lib/api/schemas";
  import { cn } from "$lib/utils";

  // 選択肢のみ（単一選択 = radio / 複数選択 = checkbox）。記述式は自動採点が難しいため廃止。
  // 複数選択の回答は選択 id をカンマ区切りの文字列で保持する（quiz_answers.value は単一の文字列）。
  type Props = { question: QuizQuestion; value: string; onanswer: (value: string) => void };
  const { question, value, onanswer }: Props = $props();

  const selected = $derived(value ? value.split(",").filter(Boolean) : []);
  function toggleMulti(id: string) {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    onanswer([...next].sort().join(","));
  }
</script>

{#if question.kind === "multiple_select"}
  <div class="space-y-2">
    {#each question.choices ?? [] as choice (choice.id)}
      <label
        class={cn(
          "flex cursor-pointer items-center gap-2 rounded-md border p-2.5 text-sm transition-colors hover:bg-accent/40",
          selected.includes(choice.id) && "border-primary bg-accent/40",
        )}
      >
        <input
          type="checkbox"
          checked={selected.includes(choice.id)}
          onchange={() => toggleMulti(choice.id)}
          class="accent-primary"
        />
        {choice.label}
      </label>
    {/each}
  </div>
{:else}
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
{/if}
