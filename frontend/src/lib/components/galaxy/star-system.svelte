<script lang="ts">
  import type { StarSystem } from "$lib/api/schemas";
  import { formatKc } from "$lib/format/kc";
  import StarNode from "./star-node.svelte";

  // 1 星系（モジュール）の島。所属ファイルの星を内包し、集計 KC をラベル表示する。
  const { system }: { system: StarSystem } = $props();
</script>

<div class="rounded-2xl border border-cyan-500/20 bg-slate-900/70 px-3 py-2 backdrop-blur-sm">
  <div class="flex max-w-32 flex-wrap items-center justify-center gap-2">
    {#each system.files as file (file.path)}
      <StarNode {file} />
    {/each}
  </div>
  <div class="mt-1.5 text-center text-[10px] whitespace-nowrap text-cyan-200/70">
    {system.module} · {formatKc(system.kc)}
  </div>
</div>
