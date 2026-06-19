<script lang="ts">
  import Info from "@lucide/svelte/icons/info";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import * as m from "$lib/paraglide/messages";

  // 二軸の語彙凡例: 「コード負債 (amber) / 知識被覆 KC (teal)」を info アイコンから提示する。
  // ドット色は rank 9 の統一トークン（debt-code / debt-knowledge）と 1:1 で一致させる。
  // 祖先の Tooltip.Provider に依存しないよう自前で内包する（どの画面からでも使える）。
</script>

<Tooltip.Provider delayDuration={150}>
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        <button
          {...props}
          type="button"
          class="inline-flex text-muted-foreground transition-colors hover:text-foreground"
          aria-label={m.axis_legend_title()}
        >
          <Info class="size-3.5" />
        </button>
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content side="top" class="space-y-1">
      <div class="font-medium">{m.axis_legend_title()}</div>
      <div class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-full bg-debt-code"></span>
        {m.axis_legend_code()}
      </div>
      <div class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-full bg-debt-knowledge"></span>
        {m.axis_legend_knowledge()}
      </div>
    </Tooltip.Content>
  </Tooltip.Root>
</Tooltip.Provider>
