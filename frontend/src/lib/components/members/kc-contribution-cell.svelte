<script lang="ts">
  import * as Tooltip from "$lib/components/ui/tooltip";
  import * as m from "$lib/paraglide/messages";

  // GitLab には無い DevDebtOps 独自列。後続 issue で member.kcContribution（0..1）を 4 段階バーで描く。
  // 本 issue は枠のみ（プレースホルダ + Coming Soon ツールチップ）。
</script>

<Tooltip.Provider delayDuration={150}>
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        <span {...props} class="inline-flex items-center gap-1 text-muted-foreground">
          <span aria-hidden="true" class="font-mono text-debt-knowledge/50">▮▯▯▯</span>
          <span class="text-xs">—</span>
        </span>
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content>{m.members_kc_tooltip()}</Tooltip.Content>
  </Tooltip.Root>
</Tooltip.Provider>
