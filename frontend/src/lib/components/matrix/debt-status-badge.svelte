<script lang="ts">
  import { cn } from "$lib/utils";
  import { statusLabel } from "./labels";

  type Props = { status: string };
  const { status }: Props = $props();

  const tone: Record<string, string> = {
    open: "bg-destructive/15 text-destructive",
    in_pr: "bg-warning/15 text-warning",
    in_progress: "bg-warning/15 text-warning",
    resolved: "bg-success/15 text-success",
    dismissed: "bg-muted text-muted-foreground",
  };
</script>

<span
  class={cn(
    "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
    tone[status] ?? "bg-muted text-muted-foreground",
  )}
>
  {statusLabel(status)}
</span>
