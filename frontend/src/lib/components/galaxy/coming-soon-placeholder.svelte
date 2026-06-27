<script lang="ts">
  import Network from "@lucide/svelte/icons/network";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { Button } from "$lib/components/ui/button";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // 未解析の空状態。コンテンツ生成は Overview の「解析」に集約（issue 064）。ここでは解析（ダッシュボード）へ誘導する。
</script>

<div class="flex h-full min-h-[24rem] flex-col items-center justify-center rounded-lg border bg-card text-center">
  <div class="max-w-md space-y-4 px-6">
    <Network class="mx-auto size-12 text-muted-foreground" />
    <h2 class="font-display text-xl font-semibold">{m.galaxy_coming_title()}</h2>
    <p class="text-sm leading-relaxed text-muted-foreground">{m.galaxy_coming_desc()}</p>
    <div class="flex items-center justify-center gap-2">
      <a
        href={resolve(`/${page.params.org}/${page.params.project}`)}
        class="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        {m.analysis_run_cta()}
      </a>
      <Button variant="outline" onclick={() => galaxy.loadMock()}>{m.galaxy_coming_demo()}</Button>
    </div>
  </div>
</div>
