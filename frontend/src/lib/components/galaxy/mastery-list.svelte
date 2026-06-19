<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import type { PersonalGalaxy } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";
  import { masteryDot, masteryLabel } from "./galaxy-labels";

  // §5.5 個人認定の簡易版。KC 昇順（ブラックホール=危険を上位）に並べる。
  const { galaxy }: { galaxy: PersonalGalaxy } = $props();
  const files = $derived(galaxy.systems.flatMap((s) => s.files).sort((a, b) => a.kc - b.kc));

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const quizzesHref = $derived(resolve(`/${orgSlug}/${projectSlug}/quizzes`));
</script>

<div class="overflow-x-auto p-1">
  <table class="w-full text-sm">
    <thead>
      <tr class="text-left text-xs text-muted-foreground">
        <th class="py-1.5 pr-3 font-normal">{m.galaxy_list_status()}</th>
        <th class="py-1.5 pr-3 font-normal">{m.galaxy_list_file()}</th>
        <th class="py-1.5 pr-3 text-right font-normal">{m.galaxy_list_kc()}</th>
        <th class="py-1.5 pr-3 font-normal">{m.galaxy_list_module()}</th>
        <th class="py-1.5 font-normal"><span class="sr-only">{m.galaxy_repay_with_quiz()}</span></th>
      </tr>
    </thead>
    <tbody>
      {#each files as f (f.path)}
        <tr class="border-t">
          <td class="py-1.5 pr-3">
            <span class="inline-flex items-center gap-1.5">
              <span class={cn("size-2.5 rounded-full", masteryDot[f.mastery])}></span>
              <span class="text-xs text-muted-foreground">{masteryLabel(f.mastery)}</span>
            </span>
          </td>
          <td class="py-1.5 pr-3 font-mono text-xs">
            {f.path}
            {#if f.mastered}<Check
                class="ml-1 inline size-3 text-success"
                aria-label={m.galaxy_list_mastered()}
              />{/if}
          </td>
          <td class="py-1.5 pr-3 text-right tabular-nums">{Math.round(f.kc * 100)}%</td>
          <td class="py-1.5 pr-3 text-xs text-muted-foreground">{f.module}</td>
          <td class="py-1.5 text-right">
            {#if f.mastery === "black_hole" || f.mastery === "dim_star"}
              <a
                href={quizzesHref}
                class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium text-primary hover:underline"
              >
                {m.galaxy_repay_with_quiz()}
              </a>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
