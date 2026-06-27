<script lang="ts">
  import Radar from "@lucide/svelte/icons/radar";
  import { page } from "$app/state";
  import { cn } from "$lib/utils";
  import * as Popover from "$lib/components/ui/popover";
  import { repo } from "$lib/stores/repo-store.svelte";
  import { analysisRun, type RunContext } from "$lib/stores/analysis-run-store.svelte";
  import AnalysisRunCockpit from "$lib/components/overview/analysis-run-cockpit.svelte";
  import * as m from "$lib/paraglide/messages";

  // 解析の実行/進捗をトップバーへ集約（ダッシュボードは閲覧専用に）。プロジェクト配下のどのページからでも
  // 起動・確認できる。永続化済みジョブからの状態復元（hydrate）は常時マウントのここで行う。
  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");
  const ctx = $derived<RunContext>({
    orgSlug,
    projectSlug,
    owner: repo.connected?.owner ?? "",
    repo: repo.connected?.name ?? "",
  });

  $effect(() => {
    if (orgSlug && projectSlug) void analysisRun.hydrate(ctx);
  });
</script>

<Popover.Root>
  <Popover.Trigger>
    {#snippet child({ props })}
      <button
        {...props}
        title={m.analysis_run_cta()}
        data-tour="analysis-run"
        class={cn(
          "flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-sm transition-colors hover:bg-accent",
          analysisRun.running ? "text-debt-knowledge" : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Radar class={cn("size-4 shrink-0", analysisRun.running && "animate-spin")} />
        <span class="hidden sm:inline">{m.analysis_run_short()}</span>
        {#if analysisRun.running}
          <span class="size-1.5 shrink-0 rounded-full bg-debt-knowledge"></span>
        {/if}
      </button>
    {/snippet}
  </Popover.Trigger>
  <Popover.Content align="end" sideOffset={6} class="w-96 max-w-[calc(100vw-1rem)] p-2">
    <AnalysisRunCockpit {ctx} />
  </Popover.Content>
</Popover.Root>
