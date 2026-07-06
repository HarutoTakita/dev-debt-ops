<script lang="ts">
  import type { Pathname } from "$app/types";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { locales, localizeHref } from "$lib/paraglide/runtime";
  import { ModeWatcher } from "mode-watcher";
  import { Toaster } from "$lib/components/ui/sonner";
  import SessionTimeoutDialog from "$lib/components/shell/session-timeout-dialog.svelte";
  import { auth } from "$lib/stores/auth.svelte";
  import { sessionTimeout } from "$lib/stores/session-timeout.svelte";
  import "./layout.css";
  let { children } = $props();

  // 無操作セッションタイムアウト（全認証ページ対象、非デモのみ）。未認証(/login 等)・デモは対象外。
  // 認証状態はリアクティブなので、ログイン成立で開始・ログアウトで停止する。
  $effect(() => {
    if (auth.isAuthenticated && !auth.isDemo) sessionTimeout.start();
    else sessionTimeout.stop();
    return () => sessionTimeout.stop();
  });
</script>

<ModeWatcher defaultMode="dark" />
<Toaster />
<SessionTimeoutDialog />
{@render children()}

<!-- Paraglide needs locale-prefixed links in the DOM for SSG to discover all locale variants -->
<div style="display:none">
  {#each locales as locale (locale)}
    <a href={resolve(localizeHref(page.url.pathname, { locale }) as Pathname)}>{locale}</a>
  {/each}
</div>
