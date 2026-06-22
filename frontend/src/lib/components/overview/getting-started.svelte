<script lang="ts">
  import X from "@lucide/svelte/icons/x";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { project } from "$lib/stores/project-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // 「最初の 30 秒」を導く、閉じられるオンボーディングカード。閉じた状態は project-store が localStorage 永続。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const key = $derived(`${orgSlug}/${projectSlug}`);
  const dismissed = $derived(project.isGettingStartedDismissed(key));

  const cards = $derived([
    { emoji: "🗺️", label: m.getting_started_galaxy(), href: resolve(`/${orgSlug}/${projectSlug}/galaxy`) },
    { emoji: "📊", label: m.getting_started_matrix(), href: resolve(`/${orgSlug}/${projectSlug}/matrix`) },
    { emoji: "📚", label: m.getting_started_quiz(), href: resolve(`/${orgSlug}/${projectSlug}/learning`) },
    { emoji: "📂", label: m.getting_started_repos(), href: resolve(`/${orgSlug}/${projectSlug}/repos`) },
  ]);
</script>

{#if !dismissed}
  <section class="rounded-lg border bg-card p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="text-sm font-semibold">{m.getting_started_title()}</h2>
      <button
        type="button"
        onclick={() => project.dismissGettingStarted(key)}
        aria-label={m.getting_started_dismiss()}
        title={m.getting_started_dismiss()}
        class="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <X class="size-4" />
      </button>
    </div>
    <div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
      {#each cards as c (c.href)}
        <a
          href={c.href}
          class="flex items-center gap-2 rounded-md border border-sidebar-border bg-surface-sunken p-3 text-sm transition-colors hover:border-debt-knowledge/50 hover:bg-accent/40"
        >
          <span class="text-xl">{c.emoji}</span>
          <span class="min-w-0 flex-1 font-medium">{c.label}</span>
        </a>
      {/each}
    </div>
  </section>
{/if}
