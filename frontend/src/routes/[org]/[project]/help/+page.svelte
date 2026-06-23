<script lang="ts">
  import { onboarding } from "$lib/stores/onboarding-store.svelte";
  import { Button } from "$lib/components/ui/button";
  import * as m from "$lib/paraglide/messages";

  // ヘルプページ（issue 066）。サイドバー左下の ? から到達。オンボーディングガイドを再生でき、
  // 各メニューの要点（ツアーと同じ文言を再利用）を一覧する。
  const menus = [
    { label: m.nav_galaxy, body: m.tour_galaxy_body },
    { label: m.nav_matrix, body: m.tour_matrix_body },
    { label: m.nav_knowledge_hub, body: m.tour_knowledge_body },
    { label: m.nav_repos, body: m.tour_repos_body },
    { label: m.nav_settings, body: m.tour_settings_body },
  ];
</script>

<svelte:head>
  <title>{m.nav_help()} · Rosetta</title>
</svelte:head>

<div class="mx-auto max-w-2xl space-y-6 p-4">
  <section class="space-y-3 rounded-lg border bg-card p-4">
    <p class="text-sm text-muted-foreground">{m.help_intro()}</p>
    <Button onclick={() => onboarding.start()}>{m.help_replay_tour()}</Button>
  </section>

  <section class="space-y-3">
    <h2 class="font-display text-sm font-semibold">{m.help_menus_title()}</h2>
    <ul class="space-y-2">
      {#each menus as menu (menu.label())}
        <li class="rounded-md border bg-card p-3 text-sm">
          <span class="font-medium">{menu.label()}</span>
          <span class="text-muted-foreground"> — {menu.body()}</span>
        </li>
      {/each}
    </ul>
  </section>
</div>
