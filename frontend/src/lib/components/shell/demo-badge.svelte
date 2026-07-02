<script lang="ts">
  import FlaskConical from "@lucide/svelte/icons/flask-conical";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { auth } from "$lib/stores/auth.svelte";

  // ゲストデモ環境の常設バッジ（issue 069）。従来はページ最上部の常設バナーだったが、常時表示が冗長なため
  // トップバーの小さな「デモ環境」四角枠バッジ（オレンジ）に置き換え、ホバーで説明ツールチップを出す。
</script>

{#if auth.isDemo}
  <Tooltip.Provider delayDuration={150}>
    <Tooltip.Root>
      <Tooltip.Trigger>
        {#snippet child({ props })}
          <span
            {...props}
            role="status"
            class="inline-flex items-center gap-1 rounded-md border border-amber-300/60 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-200"
          >
            <FlaskConical class="size-3.5 shrink-0" />
            デモ環境
          </span>
        {/snippet}
      </Tooltip.Trigger>
      <Tooltip.Content class="max-w-xs text-center leading-relaxed">
        これはサンプルデータのデモ環境です。GitHub 連携が必要な操作は利用できません。GitHub
        でサインインすると、自分のリポジトリを解析できます。
      </Tooltip.Content>
    </Tooltip.Root>
  </Tooltip.Provider>
{/if}
