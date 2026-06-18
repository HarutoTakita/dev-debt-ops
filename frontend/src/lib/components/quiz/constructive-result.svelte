<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import Sprout from "@lucide/svelte/icons/sprout";
  import type { QuizResult } from "$lib/api/schemas";
  import { Button } from "$lib/components/ui/button";
  import KcMeter from "./kc-meter.svelte";
  import * as m from "$lib/paraglide/messages";

  // 「正解/不正解」を出さない建設的フレーミング。理解していたこと / 学ぶ余地 + KC カウントアップ。
  type Props = { result: QuizResult; learningHref: string };
  const { result, learningHref }: Props = $props();
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
      <ul class="mt-2 space-y-1 text-sm text-muted-foreground">
        {#each result.gap_concepts as c (c.id)}<li>・{c.label}</li>{/each}
      </ul>
    </div>
  </div>

  <div class="text-center">
    <Button href={learningHref}>{m.quiz_result_cta()} →</Button>
  </div>
</div>
