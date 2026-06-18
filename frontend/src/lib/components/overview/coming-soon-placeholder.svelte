<script lang="ts">
  import type { Snippet } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import * as m from "$lib/paraglide/messages";

  // データ未取得時のプレースホルダ。背後にモックで描いた本番同等レイアウトを薄く透かし、
  // 「ここに何が出るか」を場所として見せる（GitLab の空状態を地層メタファーで独自化）。
  type Props = { ctaHref?: string; preview?: Snippet };
  const { ctaHref, preview }: Props = $props();
</script>

<div class="relative h-full overflow-hidden">
  {#if preview}
    <div class="pointer-events-none absolute inset-0 overflow-hidden opacity-40 blur-[1px]" aria-hidden="true">
      {@render preview()}
    </div>
  {/if}

  <div class="absolute inset-0 flex items-center justify-center bg-background/60 p-4">
    <div class="max-w-md rounded-lg border bg-card p-6 text-center shadow-sm">
      <!-- 地層ストライプ装飾（アンバー = 負債層 / ティール = 理解層） -->
      <div class="mx-auto mb-4 w-24 space-y-0.5">
        <div class="h-0.5 rounded bg-debt-code/80"></div>
        <div class="h-0.5 rounded bg-debt-code/50"></div>
        <div class="h-0.5 rounded bg-debt-knowledge/60"></div>
      </div>
      <h2 class="font-display text-lg font-semibold">{m.overview_coming_title()}</h2>
      <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{m.overview_coming_desc()}</p>
      {#if ctaHref}
        <div class="mt-4">
          <Button href={ctaHref}>{m.overview_coming_cta()}</Button>
        </div>
      {/if}
    </div>
  </div>
</div>
