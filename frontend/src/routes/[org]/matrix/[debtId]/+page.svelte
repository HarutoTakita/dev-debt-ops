<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import { resolve } from "$app/paths";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import FileViewer from "$lib/components/repo/file-viewer.svelte";
  import DebtMetaPanel from "$lib/components/matrix/debt-meta-panel.svelte";
  import DebtStatusBadge from "$lib/components/matrix/debt-status-badge.svelte";
  import DebtActions from "$lib/components/matrix/debt-actions.svelte";
  import * as m from "$lib/paraglide/messages";

  let { data } = $props();
  const debt = $derived(data.debt);
  const orgSlug = $derived(data.orgSlug);
</script>

<svelte:head>
  <title>{debt.file_path} · Rosetta</title>
</svelte:head>

<Tooltip.Provider delayDuration={150}>
  <div class="mx-auto flex max-w-5xl flex-col gap-3 p-4">
    <!-- 上部: 戻る + パス + ステータス -->
    <div class="flex flex-wrap items-center gap-2">
      <a
        href={resolve(`/${orgSlug}/matrix`)}
        class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft class="size-4" />
        {m.matrix_back()}
      </a>
      <span class="min-w-0 flex-1 truncate text-right font-mono text-sm font-medium">{debt.file_path}</span>
      <DebtStatusBadge status={debt.status} />
    </div>

    <DebtActions {orgSlug} debtId={debt.id} />

    <!-- 本体: 左 = 該当コード + 根拠 / 右 = メタパネル -->
    <div class="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
      <div class="flex flex-col gap-3">
        <div class="overflow-hidden rounded-lg border bg-card">
          <div class="border-b px-3 py-1.5 text-xs text-muted-foreground">{m.debt_evidence()}</div>
          <div class="max-h-80 overflow-auto">
            <FileViewer
              path={debt.file_path}
              content={debt.code_snippet}
              size={debt.code_snippet.length}
              loading={false}
            />
          </div>
        </div>
        <div class="rounded-lg border bg-card p-4">
          <div class="text-xs font-medium text-muted-foreground">{m.debt_archaeology()}</div>
          <p class="mt-1.5 text-sm leading-relaxed">
            {#if debt.kind === "code"}{debt.archaeology_notes}{:else}{m.debt_knowledge_note()}{/if}
          </p>
        </div>
      </div>

      <DebtMetaPanel {debt} />
    </div>
  </div>
</Tooltip.Provider>
