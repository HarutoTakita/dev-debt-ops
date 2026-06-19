<script lang="ts">
  import { resolve } from "$app/paths";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import type { FileMastery } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import * as m from "$lib/paraglide/messages";
  import { masteryLabel } from "./galaxy-labels";

  // 1 ファイル = 1 星。KC を発光強度に、mastery で見た目を分岐。要 Tooltip.Provider 祖先。
  const { file }: { file: FileMastery } = $props();

  // FileMastery は debt id を持たないため、返済導線はファイル絞りなしの quizzes へ（issue-019 rank 8/21）。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const quizzesHref = $derived(resolve(`/${orgSlug}/${projectSlug}/quizzes`));

  const glow = $derived(Math.max(0.25, file.kc));
  const cls = $derived(
    {
      star: "bg-cyan-300 shadow-[0_0_12px_4px_rgba(103,232,249,0.9)]",
      dim_star: "bg-teal-400/60 shadow-[0_0_6px_2px_rgba(45,212,191,0.5)]",
      black_hole: "border border-red-500/80 bg-red-950 shadow-[0_0_10px_2px_rgba(239,68,68,0.55)]",
      unexplored: "border border-dashed border-slate-600 bg-transparent",
    }[file.mastery],
  );
</script>

<Tooltip.Root>
  <Tooltip.Trigger>
    {#snippet child({ props })}
      <button
        {...props}
        type="button"
        aria-label={file.path}
        onclick={() => goto(quizzesHref)}
        style:opacity={file.mastery === "unexplored" ? 1 : glow}
        class={cn("size-3 rounded-full transition hover:scale-150", cls)}
      ></button>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content side="top">
    <span class="font-mono">{file.path}</span>
    · KC {Math.round(file.kc * 100)}% · {masteryLabel(file.mastery)}
    <a href={quizzesHref} class="mt-1 block font-medium text-primary hover:underline">
      {m.galaxy_repay_with_quiz()}
    </a>
  </Tooltip.Content>
</Tooltip.Root>
