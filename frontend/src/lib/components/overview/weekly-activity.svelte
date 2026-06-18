<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import GraduationCap from "@lucide/svelte/icons/graduation-cap";
  import type { WeeklyActivity } from "$lib/api/schemas";
  import * as m from "$lib/paraglide/messages";

  type Props = { activity: WeeklyActivity };
  const { activity }: Props = $props();
</script>

<div>
  <div class="text-sm font-medium">{m.overview_weekly_title()}</div>
  <ul class="mt-3 space-y-2.5 text-sm">
    <li class="flex items-center gap-2">
      <Bot class="size-4 shrink-0 text-debt-code" />
      <span>{m.overview_weekly_code_agent()}</span>
      <span class="ml-auto text-muted-foreground tabular-nums">
        {m.overview_weekly_prs({ prs: activity.code_agent_prs, merged: activity.code_agent_merged })}
      </span>
    </li>
    <li class="flex items-center gap-2">
      <GraduationCap class="size-4 shrink-0 text-debt-knowledge" />
      <span>{m.overview_weekly_knowledge_agent()}</span>
      <span class="ml-auto text-muted-foreground tabular-nums">
        {m.overview_weekly_quizzes({
          quizzes: activity.knowledge_agent_quizzes,
          passed: activity.knowledge_agent_passed,
        })}
      </span>
    </li>
  </ul>
</div>
