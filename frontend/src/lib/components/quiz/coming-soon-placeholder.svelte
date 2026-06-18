<script lang="ts">
  import type { Snippet } from "svelte";

  // 汎用 Coming Soon プレースホルダ（GlEmptyState の構図を Rosetta ブランドで）。
  type Props = { title: string; description: string; eyebrow?: string; action?: Snippet };
  const { title, description, eyebrow, action }: Props = $props();
</script>

<div class="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-16 text-center">
  {#if eyebrow}
    <span class="rounded-full bg-debt-knowledge/15 px-2.5 py-0.5 text-xs font-medium text-debt-knowledge">
      ◎ {eyebrow}
    </span>
  {/if}
  <h2 class="font-display text-2xl tracking-tight">{title}</h2>
  <p class="text-sm leading-relaxed text-muted-foreground">{description}</p>
  {#if action}<div class="pt-1">{@render action()}</div>{/if}
</div>
