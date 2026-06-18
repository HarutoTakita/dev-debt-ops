<script lang="ts">
  import Search from "@lucide/svelte/icons/search";
  import { toast } from "svelte-sonner";
  import * as m from "$lib/paraglide/messages";

  // パレット本体は別 issue。ここでは見た目と ⌘K ショートカット枠だけを提供する。
  function open() {
    toast.info(m.shell_coming_soon({ feature: m.shell_command_palette() }));
  }

  function onKeydown(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      open();
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<button
  type="button"
  onclick={open}
  class="flex h-8 w-full max-w-64 items-center gap-2 rounded-md border border-border bg-background/50 px-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
>
  <Search class="size-4 shrink-0" />
  <span class="flex-1 truncate text-left">{m.shell_command_palette()}</span>
  <kbd class="hidden items-center gap-0.5 rounded border border-border px-1 font-mono text-[10px] sm:inline-flex"
    >⌘K</kbd
  >
</button>
