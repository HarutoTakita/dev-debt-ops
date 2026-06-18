<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { allNavItems, isActiveRoute, type NavContext } from "$lib/config/nav";

  const orgSlug = $derived(page.params.org ?? "");
  const ctx: NavContext = $derived({ orgSlug, repoConnected: repo.connected !== null });
  // 「理解の階層」: Org > 現在の区分。リポジトリ構造ではなく理解度の階層を主語にする。
  const current = $derived(
    allNavItems.find((i) => i.id !== "overview" && isActiveRoute(i.route(ctx), page.url.pathname)),
  );
</script>

<nav class="flex min-w-0 items-center gap-1.5 text-sm" aria-label="breadcrumb">
  <a href={resolve(`/${orgSlug}`)} class="truncate font-display font-medium hover:underline">{orgSlug}</a>
  {#if current}
    <ChevronRight class="size-3.5 shrink-0 text-muted-foreground" />
    <span class="truncate text-muted-foreground">{current.label()}</span>
  {/if}
</nav>
