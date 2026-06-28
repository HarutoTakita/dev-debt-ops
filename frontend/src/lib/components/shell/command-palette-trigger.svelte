<script lang="ts">
  import Search from "@lucide/svelte/icons/search";
  import CommandPalette from "./command-palette.svelte";
  import * as m from "$lib/paraglide/messages";

  // コマンドパレットを開くトリガー。ボタンクリックと ⌘K / Ctrl+K のどちらでも開閉する。
  let open = $state(false);

  function onKeydown(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      open = !open;
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<button
  type="button"
  onclick={() => (open = true)}
  class="flex h-8 w-full max-w-64 items-center gap-2 rounded-md border border-border bg-background/50 px-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
>
  <Search class="size-4 shrink-0" />
  <span class="flex-1 truncate text-left">{m.shell_command_palette()}</span>
  <kbd
    class="pointer-events-none hidden items-center gap-0.5 rounded border border-border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground sm:inline-flex"
  >
    ⌘K
  </kbd>
</button>

<CommandPalette bind:open />
