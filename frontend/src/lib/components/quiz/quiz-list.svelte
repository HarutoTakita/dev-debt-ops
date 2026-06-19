<script lang="ts">
  import ArrowRight from "@lucide/svelte/icons/arrow-right";
  import { resolve } from "$app/paths";
  import type { QuizListItem } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  // 受験可能クイズ一覧（カード: ファイルパス・KC 低下理由・問題数・推定分）。
  type Props = { quizzes: QuizListItem[]; orgSlug: string; projectSlug: string };
  const { quizzes, orgSlug, projectSlug }: Props = $props();
</script>

<ul class="flex flex-col gap-3">
  {#each quizzes as q (q.session_id)}
    <li>
      <a
        href={resolve(`/${orgSlug}/${projectSlug}/quizzes/${q.session_id}`)}
        class="block rounded-lg border bg-card p-4 transition-colors hover:bg-accent/40"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate font-mono text-sm font-medium">{q.file_path}</span>
          <span class="flex shrink-0 items-center gap-1 text-xs text-primary">
            {m.quiz_list_take()}
            <ArrowRight class="size-3.5" />
          </span>
        </div>
        <p class="mt-1.5 text-xs text-muted-foreground">{m.quiz_list_reason()}: {q.reason}</p>
        <p class="mt-1 text-xs text-muted-foreground">
          {m.quiz_list_questions({ count: q.question_count })} · {m.quiz_list_minutes({ min: q.estimated_minutes })}
        </p>
      </a>
    </li>
  {/each}
</ul>
