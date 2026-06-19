<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // Settings 共通シェル（見出し + サブナビ）。Settings は IA 上、understand 系より下の末尾固定。
  let { children } = $props();
  const orgSlug = $derived(page.params.org ?? "");
  const onMembers = $derived(page.url.pathname.endsWith("/settings/members"));
</script>

<div class="mx-auto max-w-3xl p-4">
  <h1 class="font-display text-xl font-semibold">{m.nav_settings()}</h1>
  <nav class="mt-3 flex gap-1 border-b" aria-label="settings">
    <a
      href={resolve(`/${orgSlug}/settings/members`)}
      class={cn(
        "border-b-2 px-3 py-2 text-sm transition-colors",
        onMembers ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {m.admin_members_title()}
    </a>
  </nav>
  <div class="mt-4">{@render children()}</div>
</div>
