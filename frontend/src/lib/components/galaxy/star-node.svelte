<script lang="ts">
  import { resolve } from "$app/paths";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import type { FileMastery } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import * as m from "$lib/paraglide/messages";
  import { formatKc } from "$lib/format/kc";
  import { masteryLabel } from "./galaxy-labels";

  // 1 ファイル = 1 星。KC を発光強度 + サイズに、mastery で見た目（色 + 形）を分岐。要 Tooltip.Provider 祖先。
  const { file }: { file: FileMastery } = $props();

  // FileMastery は debt id を持たないため、返済導線はファイル絞りなしの quizzes へ（issue-019 rank 8/21）。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const quizzesHref = $derived(resolve(`/${orgSlug}/${projectSlug}/quizzes`));

  const glow = $derived(Math.max(0.25, file.kc));
  // rank20: KC に応じてサイズもスケール（理解度を発光 + 大きさの二重符号に）。
  const px = $derived(Math.round(9 + file.kc * 9)); // 9〜18px
  // ティール = 知識（明るさ = 被覆度）/ 赤(destructive) = 危険専用。色だけに頼らず形でも分岐（rank10）:
  // star=塗り / dim_star=内側リング / black_hole=中空+中心ホール / unexplored=破線。
  const cls = $derived(
    {
      star: "bg-debt-knowledge shadow-[0_0_12px_4px_rgba(45,212,191,0.55)]",
      dim_star: "bg-debt-knowledge/60 ring-1 ring-inset ring-background/50 shadow-[0_0_6px_2px_rgba(45,212,191,0.35)]",
      black_hole: "border border-destructive/80 bg-destructive/25 shadow-[0_0_10px_2px_rgba(239,68,68,0.5)]",
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
        style:width={`${px}px`}
        style:height={`${px}px`}
        class={cn(
          // before:= 不可視の ~24px ヒットターゲット（見た目は変えない）。focus-visible でリング表示。
          "relative rounded-full transition before:absolute before:-inset-2 before:rounded-full before:content-['']",
          "hover:scale-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none motion-reduce:hover:scale-100",
          cls,
        )}
      >
        {#if file.mastery === "black_hole"}
          <!-- 中心ホール（色に依存しない形の手がかり） -->
          <span
            class="pointer-events-none absolute top-1/2 left-1/2 h-1/3 w-1/3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-background/80"
          ></span>
        {/if}
      </button>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content side="top">
    <span class="font-mono">{file.path}</span>
    · {formatKc(file.kc)} · {masteryLabel(file.mastery)}
    <a href={quizzesHref} class="mt-1 block font-medium text-primary hover:underline">
      {m.galaxy_repay_with_quiz()}
    </a>
  </Tooltip.Content>
</Tooltip.Root>
