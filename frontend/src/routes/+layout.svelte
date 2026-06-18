<script lang="ts">
  import type { Pathname } from "$app/types";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { locales, localizeHref } from "$lib/paraglide/runtime";
  import { ModeWatcher } from "mode-watcher";
  import { Toaster } from "$lib/components/ui/sonner";
  import "./layout.css";
  let { children } = $props();
</script>

<ModeWatcher defaultMode="dark" />
<Toaster />
{@render children()}

<!-- Paraglide needs locale-prefixed links in the DOM for SSG to discover all locale variants -->
<div style="display:none">
  {#each locales as locale (locale)}
    <a href={resolve(localizeHref(page.url.pathname, { locale }) as Pathname)}>{locale}</a>
  {/each}
</div>
