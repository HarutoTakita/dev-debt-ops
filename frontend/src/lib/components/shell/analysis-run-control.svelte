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

  // 新規プロジェクト（リポジトリ接続済み）でまだ一度も解析していないときは、解析ボタンを点滅させ、
  // ボタン下に案内の吹き出しを出して最初の一歩へ誘導する（解析ウィンドウを開いている間は隠す）。
  let popoverOpen = $state(false);
  const needsFirstRun = $derived(repo.connected != null && !analysisRun.started && !analysisRun.running);
  const showGuide = $derived(needsFirstRun && !popoverOpen);
</script>

<div class="relative flex items-center">
  <Popover.Root bind:open={popoverOpen}>
    <Popover.Trigger>
      {#snippet child({ props })}
        <button
          {...props}
          title={needsFirstRun ? m.analysis_run_guide() : m.analysis_run_cta()}
          data-tour="analysis-run"
          class={cn(
            "flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors hover:bg-accent",
            analysisRun.running
              ? "border-border text-debt-knowledge"
              : needsFirstRun
                ? "animate-pulse border-debt-knowledge text-debt-knowledge"
                : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          <Radar class={cn("size-4 shrink-0", analysisRun.running && "animate-spin")} />
          <span class="hidden sm:inline">{m.analysis_run_short()}</span>
          {#if analysisRun.running || needsFirstRun}
            <span class="size-1.5 shrink-0 rounded-full bg-debt-knowledge"></span>
          {/if}
        </button>
      {/snippet}
    </Popover.Trigger>
    <Popover.Content align="end" sideOffset={6} class="w-96 max-w-[calc(100vw-1rem)] p-2">
      <AnalysisRunCockpit {ctx} />
    </Popover.Content>
  </Popover.Root>

  <!-- 未解析プロジェクトでは、ボタン下に案内の吹き出しを表示（ホバー不要）。解析ウィンドウを開いている間は隠す。
       クリックを妨げないよう pointer-events-none。 -->
  {#if showGuide}
    <div
      class="pointer-events-none absolute top-full right-0 z-50 mt-2 w-56 rounded-md border border-debt-knowledge/40 bg-popover px-2.5 py-1.5 text-xs leading-snug text-popover-foreground shadow-md"
    >
      <!-- 吹き出しの矢印（ボタンを指す。align=end に合わせ右寄せ） -->
      <div
        class="absolute -top-1 right-3 size-2 rotate-45 border-t border-l border-debt-knowledge/40 bg-popover"
      ></div>
      {m.analysis_run_guide()}
    </div>
  {/if}
</div>
