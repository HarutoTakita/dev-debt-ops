<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Check from "@lucide/svelte/icons/check";
  import X from "@lucide/svelte/icons/x";
  import Circle from "@lucide/svelte/icons/circle";
  import { cn } from "$lib/utils";
  import type { AgentStatus } from "$lib/api/schemas";

  // CiIcon 写像。running 系（スキャン/分析/PR作成/クイズ）は回転でライブ感を出す。
  let { status }: { status: AgentStatus } = $props();

  const RUNNING = new Set<AgentStatus>(["scanning", "analyzing", "creating_pr", "running_quiz"]);
  const color: Record<AgentStatus, string> = {
    scanning: "text-blue-500",
    analyzing: "text-blue-500",
    creating_pr: "text-violet-500",
    running_quiz: "text-success",
    succeeded: "text-success",
    failed: "text-destructive",
    pending: "text-muted-foreground/50",
  };
</script>

{#if RUNNING.has(status)}
  <LoaderCircle class={cn("size-4 shrink-0 animate-spin", color[status])} />
{:else if status === "succeeded"}
  <Check class={cn("size-4 shrink-0", color[status])} />
{:else if status === "failed"}
  <X class={cn("size-4 shrink-0", color[status])} />
{:else}
  <Circle class={cn("size-4 shrink-0", color[status])} />
{/if}
