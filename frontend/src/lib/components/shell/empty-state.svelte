<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    title,
    description,
    illustration,
    action,
  }: {
    title: string;
    description?: string;
    illustration?: Snippet;
    action?: Snippet;
  } = $props();
</script>

<div class="mx-auto flex max-w-md flex-col items-center gap-4 px-6 py-16 text-center">
  {#if illustration}
    <div class="text-subtle">{@render illustration()}</div>
  {/if}
  <h2 class="font-display text-2xl tracking-tight">{title}</h2>
  {#if description}
    <p class="text-sm leading-relaxed text-muted-foreground">{description}</p>
  {/if}
  {#if action}
    <div class="pt-1">{@render action()}</div>
  {/if}
</div>
