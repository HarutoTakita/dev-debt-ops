<script lang="ts">
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import type { CodeWalkthroughStep } from "$lib/api/schemas";
  import CodeLines from "./code-lines.svelte";
  import * as m from "$lib/paraglide/messages";

  // コード理解ウォークスルー: ソースを行ごとに表示し、step ごとに該当行をハイライト＋スクロールしながら解説する。
  type Props = { content: string; path: string; steps: CodeWalkthroughStep[] };
  const { content, path, steps }: Props = $props();

  let idx = $state(0);
  const active = $derived(steps[idx]);
  const total = $derived(steps.length);

  function go(next: number) {
    idx = Math.max(0, Math.min(total - 1, next));
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "ArrowRight") go(idx + 1);
    else if (e.key === "ArrowLeft") go(idx - 1);
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start">
  <!-- 左: 行ごとのソース表示（該当 step の範囲をハイライト） -->
  <CodeLines {content} {path} highlightStart={active?.start_line ?? 0} highlightEnd={active?.end_line ?? 0} />

  <!-- 右: 現在 step の解説 + ナビ。固定高 + 解説をスクロール領域にして移動ボタンを毎ステップ同じ位置に固定。 -->
  <div class="lg:sticky lg:top-4">
    <div class="flex min-h-[18rem] flex-col rounded-lg border bg-card p-4 lg:h-[72vh]">
      <div class="flex shrink-0 items-center justify-between gap-2">
        <span class="text-xs font-medium text-muted-foreground tabular-nums">
          {m.walkthrough_step({ current: total === 0 ? 0 : idx + 1, total })}
        </span>
        {#if active}
          <span class="text-xs text-muted-foreground tabular-nums">
            L{active.start_line}{active.end_line !== active.start_line ? `–${active.end_line}` : ""}
          </span>
        {/if}
      </div>
      <div class="mt-2 flex-1 overflow-auto">
        {#if active}
          {#if active.title}
            <h3 class="font-display text-sm font-semibold text-debt-knowledge">{active.title}</h3>
          {/if}
          <p class="mt-1.5 text-sm leading-relaxed">{active.explanation}</p>
        {:else}
          <p class="text-sm text-muted-foreground">{m.walkthrough_empty()}</p>
        {/if}
      </div>
      <div class="mt-3 flex shrink-0 items-center justify-between gap-2 border-t pt-3">
        <button
          type="button"
          onclick={() => go(idx - 1)}
          disabled={idx <= 0}
          class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40 disabled:opacity-40"
        >
          <ChevronLeft class="size-3.5" />
          {m.walkthrough_prev()}
        </button>
        <button
          type="button"
          onclick={() => go(idx + 1)}
          disabled={idx >= total - 1}
          class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium text-debt-knowledge hover:bg-accent/40 disabled:opacity-40"
        >
          {m.walkthrough_next()}
          <ChevronRight class="size-3.5" />
        </button>
      </div>
    </div>
  </div>
</div>
