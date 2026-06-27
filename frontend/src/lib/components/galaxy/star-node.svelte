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

  // グラフのノード（1 ファイル = 1 ノード）。サイズで理解度、色 + 形で理解ステータスを表す。要 Tooltip.Provider 祖先。
  const { file }: { file: FileMastery } = $props();

  // FileMastery は debt id を持たないため、返済導線はファイル絞りなしの quizzes へ（issue-019 rank 8/21）。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const quizzesHref = $derived(resolve(`/${orgSlug}/${projectSlug}/learning`));

  // 理解度に応じてノードサイズをスケール（大きいほど理解が進んでいる）。
  const px = $derived(Math.round(10 + file.kc * 8)); // 10〜18px
  // ティール = 理解（被覆度）/ 赤(destructive) = 未理解。色だけに頼らず形でも分岐:
  // star=塗り / dim_star=内側リング / black_hole=中空リング / unexplored=破線。
  const cls = $derived(
    {
      star: "bg-debt-knowledge border border-debt-knowledge",
      dim_star: "bg-debt-knowledge/40 ring-1 ring-inset ring-debt-knowledge",
      black_hole: "border-2 border-destructive bg-destructive/10",
      unexplored: "border border-dashed border-muted-foreground bg-background",
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
        style:width={`${px}px`}
        style:height={`${px}px`}
        class={cn(
          // before:= 不可視の ~24px ヒットターゲット（見た目は変えない）。focus-visible でリング表示。
          "relative rounded-full transition before:absolute before:-inset-2 before:rounded-full before:content-['']",
          "hover:scale-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none motion-reduce:hover:scale-100",
          cls,
        )}
      ></button>
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
