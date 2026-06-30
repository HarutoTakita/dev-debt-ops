<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import { resolve } from "$app/paths";
  import type { CodeDebt } from "$lib/api/schemas";
  import { categoryLabel, severityLabel } from "$lib/components/matrix/labels";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 選択中ファイルの技術負債を「コンパクトに」一覧する補助パネル（本体はコードビューのため小さく）。
  // ブロックをクリックすると該当コードをハイライト（onhighlight）。詳細リンクはコード改善ページへ。
  type Props = {
    orgSlug: string;
    projectSlug: string;
    debts: CodeDebt[];
    onhighlight?: (debt: CodeDebt) => void;
    activeId?: string | null;
  };
  const { orgSlug, projectSlug, debts, onhighlight, activeId = null }: Props = $props();
</script>

<div class="flex flex-col gap-1 p-2">
  <h3 class="px-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
    {m.code_improve_file_heading()}
  </h3>
  {#if debts.length === 0}
    <p class="px-1 text-[11px] text-muted-foreground">{m.code_improve_file_empty()}</p>
  {:else}
    <ul class="flex flex-col gap-1">
      {#each debts as d (d.id)}
        <li
          class={cn(
            "flex items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-xs",
            activeId === d.id && "border-debt-knowledge ring-1 ring-debt-knowledge/40",
          )}
        >
          <button
            type="button"
            onclick={() => onhighlight?.(d)}
            title={d.archaeology_notes}
            class="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:text-foreground"
          >
            <span class="shrink-0 font-medium">{categoryLabel(d)}</span>
            <span class="shrink-0 text-muted-foreground">· {severityLabel(d.severity)}</span>
            {#if d.archaeology_notes}
              <span class="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{d.archaeology_notes}</span>
            {/if}
          </button>
          <a
            href={resolve(`/${orgSlug}/${projectSlug}/matrix/${d.id}`)}
            class="inline-flex shrink-0 items-center gap-0.5 text-[11px] font-medium text-primary hover:underline"
          >
            {m.code_improve_view_detail()}
            <ChevronRight class="size-3" />
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</div>
