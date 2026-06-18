<script lang="ts">
  import { cn } from "$lib/utils";
  import Logo from "$lib/components/logo.svelte";
  import * as m from "$lib/paraglide/messages";

  // 汎用 Coming Soon 空状態（GlEmptyState 構図を Rosetta ブランドで）。
  type Props = { title: string; description: string; eta?: string; class?: string };
  const { title, description, eta, class: className }: Props = $props();
</script>

<div class={cn("flex h-full flex-col items-center justify-center gap-4 px-8 py-16 text-center", className)}>
  <Logo class="size-12 text-debt-knowledge/60" />
  <span class="rounded-full bg-muted px-3 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
    {m.coming_soon_badge()}
  </span>
  <h2 class="font-display text-xl font-semibold">{title}</h2>
  <p class="max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
  {#if eta}
    <p class="text-xs text-muted-foreground">{m.coming_soon_eta({ eta })}</p>
  {/if}
</div>
