<script lang="ts">
  import type { AssignedDeveloper } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as Tooltip from "$lib/components/ui/tooltip";

  // certified_via + coverage で「理解している人」と「形式レビューだけ／未理解の人」を視覚区別する。
  // 要 Tooltip.Provider 祖先（呼び出し側ページで包む）。
  type Props = { dev: AssignedDeveloper };
  const { dev }: Props = $props();

  const understood = $derived(
    (dev.certified_via === "quiz" || dev.certified_via === "authorship") && dev.coverage >= 0.7,
  );
  const initial = $derived(dev.github_handle.slice(0, 1).toUpperCase());
</script>

<Tooltip.Root>
  <Tooltip.Trigger>
    {#snippet child({ props })}
      <span {...props}>
        <Avatar.Root
          class={cn("size-6 border-2", understood ? "border-success" : "border-dashed border-muted-foreground/40")}
        >
          <Avatar.Fallback class={cn("text-[10px]", understood ? "bg-success/20 text-foreground" : "bg-muted")}>
            {initial}
          </Avatar.Fallback>
        </Avatar.Root>
      </span>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content side="top"
    >@{dev.github_handle} · KC {dev.coverage.toFixed(2)} · {dev.certified_via}</Tooltip.Content
  >
</Tooltip.Root>
