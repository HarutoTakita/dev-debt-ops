<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { Button } from "$lib/components/ui/button";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // 星域未観測の空状態。GlEmptyState の構図を、暗い宇宙背景 + 星（CSS）で Rosetta 独自表現に。
  // コンテンツ生成は Overview の「解析」に集約（issue 064）。ここでは解析（ダッシュボード）へ誘導する。
</script>

<div
  class="relative flex h-full min-h-[24rem] flex-col items-center justify-center overflow-hidden rounded-lg bg-slate-950 text-center"
>
  <!-- 散らばる星（装飾） -->
  <div
    class="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle,rgba(103,232,249,0.15)_1px,transparent_1px)] [background-size:32px_32px]"
  ></div>
  <div class="relative max-w-md space-y-4 px-6">
    <p class="text-5xl">🌌</p>
    <h2 class="font-display text-xl font-semibold text-cyan-100">{m.galaxy_coming_title()}</h2>
    <p class="text-sm leading-relaxed text-slate-400">{m.galaxy_coming_desc()}</p>
    <div class="flex items-center justify-center gap-2">
      <a
        href={resolve(`/${page.params.org}/${page.params.project}`)}
        class="inline-flex h-9 items-center justify-center rounded-md bg-cyan-600 px-4 text-sm font-medium text-white hover:bg-cyan-500"
      >
        {m.analysis_run_cta()}
      </a>
      <Button variant="outline" onclick={() => galaxy.loadMock()}>{m.galaxy_coming_demo()}</Button>
    </div>
  </div>
</div>
