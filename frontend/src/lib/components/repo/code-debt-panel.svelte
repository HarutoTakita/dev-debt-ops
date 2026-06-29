<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import { resolve } from "$app/paths";
  import type { CodeDebt } from "$lib/api/schemas";
  import DebtStatusBadge from "$lib/components/matrix/debt-status-badge.svelte";
  import { categoryLabel, severityLabel } from "$lib/components/matrix/labels";
  import * as m from "$lib/paraglide/messages";

  // 選択中ファイルの技術負債を一覧する。各項目はコード改善の詳細（該当コードのハイライト + 品質が低い理由の
  // 解説）へリンクする。修正 PR の自動生成は廃止（issue 210 の方針転換）。
  type Props = { orgSlug: string; projectSlug: string; debts: CodeDebt[] };
  const { orgSlug, projectSlug, debts }: Props = $props();
</script>

<div class="flex flex-col gap-2 p-3">
  <h3 class="font-display text-sm font-semibold">{m.code_improve_file_heading()}</h3>
  {#if debts.length === 0}
    <p class="text-xs text-muted-foreground">{m.code_improve_file_empty()}</p>
  {:else}
    <ul class="flex flex-col gap-2">
      {#each debts as d (d.id)}
        <li class="rounded-lg border bg-card p-3">
          <div class="flex items-center gap-2 text-sm">
            <span class="font-medium">{categoryLabel(d)}</span>
            <span class="text-muted-foreground">· {severityLabel(d.severity)}</span>
            <span class="ml-auto"><DebtStatusBadge status={d.status} /></span>
          </div>
          {#if d.archaeology_notes}
            <p class="mt-1 line-clamp-2 text-xs text-muted-foreground">{d.archaeology_notes}</p>
          {/if}
          <a
            href={resolve(`/${orgSlug}/${projectSlug}/matrix/${d.id}`)}
            class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            {m.code_improve_view_detail()}
            <ChevronRight class="size-3.5" />
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</div>
