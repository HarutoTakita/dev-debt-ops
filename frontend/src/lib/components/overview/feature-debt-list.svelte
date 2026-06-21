<script lang="ts">
  import { getFeatureDrilldown } from "$lib/api/client";
  import type { FeatureDebt, FileDebt } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import * as m from "$lib/paraglide/messages";

  // 機能/フォルダ単位の理解負債リスト（issue 056）。各ノードは KC・mastery・優先度・ファイル数・
  // 最弱ファイルを示し、クリックで配下ファイル（GET .../features/{key}）へドリルダウンする。
  type Props = { orgSlug: string; projectSlug: string; features: FeatureDebt[] };
  const { orgSlug, projectSlug, features }: Props = $props();

  let openKey = $state<string | null>(null);
  let files = $state<FileDebt[]>([]);
  let loading = $state(false);

  async function toggle(key: string) {
    if (openKey === key) {
      openKey = null;
      files = [];
      return;
    }
    openKey = key;
    loading = true;
    files = [];
    try {
      files = await getFeatureDrilldown(orgSlug, projectSlug, key);
    } catch {
      files = [];
    } finally {
      loading = false;
    }
  }

  function kcPct(kc: number): number {
    return Math.round(Math.max(0, Math.min(1, kc)) * 100);
  }
  // KC → mastery（kc_analysis の閾値と一致）。色のみに依存しないようラベルも添える。
  function masteryTone(kc: number): string {
    if (kc >= 0.7) return "text-success";
    if (kc >= 0.4) return "text-debt-knowledge";
    return "text-destructive";
  }
  // コード負債（高いほど汚い）。粒度別のコード負債軸を機能ビューでも示す（issue 057）。
  function codeTone(code: number): string {
    if (code >= 0.6) return "text-destructive";
    if (code >= 0.3) return "text-warning";
    return "text-muted-foreground";
  }
  function codePct(code: number): number {
    return Math.round(Math.max(0, Math.min(1, code)) * 100);
  }
</script>

<div class="rounded-lg border bg-card p-4">
  {#if features.length === 0}
    <p class="py-8 text-center text-sm text-muted-foreground">{m.feature_view_empty()}</p>
  {:else}
    <ul class="flex flex-col gap-2">
      {#each features as f (f.key)}
        <li class="rounded-md border">
          <button
            type="button"
            onclick={() => toggle(f.key)}
            class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-accent/40"
          >
            <span class="min-w-0 flex-1 truncate font-medium">{f.name}</span>
            <span class={cn("shrink-0 text-xs font-medium", masteryTone(f.knowledge_coverage))}>
              {m.feature_understanding()}
              {kcPct(f.knowledge_coverage)}%
            </span>
            <span class={cn("shrink-0 text-xs font-medium", codeTone(f.code_debt_score))}>
              {m.feature_code_debt()}
              {codePct(f.code_debt_score)}%
            </span>
            <span class="shrink-0 text-xs text-muted-foreground">{m.feature_files_count({ count: f.file_count })}</span
            >
            <span class="shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium">{f.priority}</span>
          </button>
          {#if openKey === f.key}
            <div class="border-t px-3 py-2">
              {#if f.weakest_file}
                <p class="mb-1 text-xs text-muted-foreground">
                  {m.feature_weakest_file()}: <span class="text-foreground">{f.weakest_file}</span>
                </p>
              {/if}
              {#if loading}
                <p class="text-xs text-muted-foreground">…</p>
              {:else}
                <ul class="flex flex-col gap-1">
                  {#each files as file (file.path)}
                    <li class="flex items-center gap-2 text-xs">
                      <span class="min-w-0 flex-1 truncate">{file.path}</span>
                      <span class={cn("shrink-0", masteryTone(file.knowledge_coverage))}>
                        {kcPct(file.knowledge_coverage)}%
                      </span>
                      <span class={cn("shrink-0", codeTone(file.code_debt_score))}>
                        {codePct(file.code_debt_score)}%
                      </span>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
