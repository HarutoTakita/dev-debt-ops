<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { project } from "$lib/stores/project-store.svelte";
  import { allNavItems, isActiveRoute, type NavContext } from "$lib/config/nav";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const projectSelected = $derived(!!page.params.project);
  const ctx: NavContext = $derived({ orgSlug, projectSlug, projectSelected });
  const projectName = $derived(project.current?.name ?? projectSlug);
  // 「理解の階層」: Org > Project（観測対象）> 現在の区分。Overview（プロジェクトルート）は省く。
  const current = $derived(
    projectSelected
      ? allNavItems.find((i) => i.id !== "overview" && isActiveRoute(i.route(ctx), page.url.pathname, i.exact))
      : undefined,
  );
</script>

<nav class="flex min-w-0 items-center gap-1.5 text-sm" aria-label="breadcrumb">
  <a href={resolve(`/${orgSlug}`)} class="truncate font-display font-medium hover:underline">{orgSlug}</a>
  {#if projectSelected}
    <ChevronRight class="size-3.5 shrink-0 text-muted-foreground" />
    <a href={resolve(`/${orgSlug}/${projectSlug}`)} class="truncate font-display font-medium hover:underline">
      {projectName}
    </a>
  {/if}
  {#if current}
    <ChevronRight class="size-3.5 shrink-0 text-muted-foreground" />
    <span class="truncate text-muted-foreground">{current.label()}</span>
  {/if}
</nav>
