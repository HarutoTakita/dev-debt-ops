<script lang="ts">
  import type { AgentProfile } from "$lib/api/schemas";
  import { cn } from "$lib/utils";

  // エージェントの人格（名前・ロール・口調）。GitLab Duo 的な汎用チャットではなく固有人格を提示。
  let { profile }: { profile: AgentProfile } = $props();

  const dot = $derived(profile.accent === "debt-code" ? "bg-debt-code" : "bg-debt-knowledge");
</script>

<div class="flex items-start gap-3">
  <span class={cn("mt-1.5 size-3 shrink-0 rounded-full", dot)}></span>
  <div>
    <div class="flex items-baseline gap-2">
      <span class="font-display text-lg font-semibold">{profile.name}</span>
      <span class="text-xs text-muted-foreground">/ {profile.role}</span>
    </div>
    <p class="mt-0.5 text-sm text-muted-foreground">{profile.tagline}</p>
  </div>
</div>
