<script lang="ts">
  import PanelLeft from "@lucide/svelte/icons/panel-left";
  import { Button } from "$lib/components/ui/button";
  import { sidebar } from "$lib/stores/sidebar-store.svelte";
  import * as m from "$lib/paraglide/messages";
</script>

<Button
  variant="ghost"
  size="icon-sm"
  onclick={() => sidebar.toggle()}
  aria-label={m.shell_toggle_sidebar()}
  title={m.shell_toggle_sidebar()}
>
  <PanelLeft />
</Button>
