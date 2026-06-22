<script lang="ts">
  import Search from "@lucide/svelte/icons/search";
  import { toast } from "svelte-sonner";
  import * as m from "$lib/paraglide/messages";

  // コマンドパレット本体は別 issue（対象外・保留）。誤った "⌘K" ヒントは出さず（ショートカットが
  // 効くと錯覚させない）、coming soon であることを明示する。⌘K keydown の横取りもしない。
  function open() {
    toast.info(m.shell_coming_soon({ feature: m.shell_command_palette() }));
  }
</script>

<button
  type="button"
  onclick={open}
  class="flex h-8 w-full max-w-64 items-center gap-2 rounded-md border border-border bg-background/50 px-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
>
  <Search class="size-4 shrink-0" />
  <span class="flex-1 truncate text-left">{m.shell_command_palette()}</span>
</button>
