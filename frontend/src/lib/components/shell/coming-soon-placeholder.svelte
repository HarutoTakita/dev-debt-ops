<script lang="ts">
  import { Button } from "$lib/components/ui/button";
  import * as m from "$lib/paraglide/messages";
  import EmptyState from "./empty-state.svelte";

  let {
    feature,
    description,
    roadmapHref = "https://github.com/HarutoTakita/mind-odyssey/issues",
  }: {
    feature: string;
    description?: string;
    roadmapHref?: string;
  } = $props();
</script>

<EmptyState title={m.shell_coming_soon({ feature })} {description}>
  {#snippet illustration()}
    <!-- Rosetta 独自の Twin ビジュアル: アンバーの堆積層（コード負債 / 地層）の上に
         ティールの星（ナレッジ負債 / 天文台）が 1 つ昇る。GitLab の汎用 illustration とは別物。 -->
    <svg viewBox="0 0 120 80" class="size-32" role="img" aria-label="Rosetta">
      <!-- 星（ナレッジ / ティール） -->
      <path class="fill-debt-knowledge" d="M86 14l2.2 5.6L94 22l-5.8 2.4L86 30l-2.2-5.6L78 22l5.8-2.4z" />
      <!-- 地層（コード負債 / アンバー）— 下にいくほど濃い堆積 -->
      <path class="fill-debt-code/30" d="M6 44c22-8 40-8 54-4s30 6 54 0v8c-24 6-40 4-54 0s-32-4-54 4z" />
      <path class="fill-debt-code/55" d="M6 56c24-6 40-4 54 0s30 4 54-2v8c-24 5-40 3-54-1s-32-3-54 3z" />
      <path class="fill-debt-code/80" d="M6 68c24-5 40-3 54 1s30 3 54-3v8H6z" />
    </svg>
  {/snippet}
  {#snippet action()}
    <Button variant="outline" href={roadmapHref} target="_blank" rel="noreferrer">
      {m.shell_roadmap_cta()}
    </Button>
  {/snippet}
</EmptyState>
