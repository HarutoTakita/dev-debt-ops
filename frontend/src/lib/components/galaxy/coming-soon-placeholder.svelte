<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { galaxy } from "$lib/stores/galaxy-store.svelte";
  import * as m from "$lib/paraglide/messages";

  // 星域未観測の空状態。GlEmptyState の構図を、暗い宇宙背景 + 星（CSS）で Rosetta 独自表現に。
  function startScan() {
    // 本実装で実スキャンへ接続。現状は Coming Soon を明示する。
    toast.info(m.galaxy_coming_toast());
  }
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
    <Button onclick={startScan} class="bg-cyan-600 text-white hover:bg-cyan-500">{m.galaxy_coming_cta()}</Button>
    <button
      type="button"
      onclick={() => galaxy.loadMock()}
      class="block w-full text-xs text-slate-500 underline hover:text-slate-300"
    >
      {m.galaxy_coming_preview()}
    </button>
  </div>
</div>
