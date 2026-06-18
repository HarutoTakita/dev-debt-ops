<script lang="ts">
  import Logo from "$lib/components/logo.svelte";
  import * as m from "$lib/paraglide/messages";

  // 未配線領域の汎用 Coming Soon（GlEmptyState の構図を Rosetta ブランドで）。
  // ui/ は読み取り専用のため agents/ 配下に配置（機能スコープの空状態）。
  let { title, description }: { title: string; description?: string } = $props();
</script>

<div
  class="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 p-8 text-center"
>
  <div class="text-muted-foreground/40"><Logo class="size-8" /></div>
  <p class="text-sm font-medium">{title}</p>
  {#if description}<p class="max-w-xs text-xs text-muted-foreground">{description}</p>{/if}
  <span class="rounded-full border px-2 py-0.5 text-[10px] tracking-wide text-muted-foreground uppercase">
    {m.agents_coming_badge()}
  </span>
</div>
