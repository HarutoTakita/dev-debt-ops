<script lang="ts">
  import { page } from "$app/state";
  import * as Tabs from "$lib/components/ui/tabs";
  import { Button } from "$lib/components/ui/button";
  import type { AgentKind } from "$lib/api/schemas";
  import { agents } from "$lib/stores/agent-store.svelte";
  import AgentProfileHeader from "$lib/components/agents/agent-profile-header.svelte";
  import NarrativeStream from "$lib/components/agents/narrative-stream.svelte";
  import AgentPipeline from "$lib/components/agents/agent-pipeline.svelte";
  import ComingSoonPlaceholder from "$lib/components/agents/coming-soon-placeholder.svelte";
  import { analysisRun } from "$lib/stores/analysis-run-store.svelte";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import * as m from "$lib/paraglide/messages";

  const orgSlug = $derived(page.params.org ?? "");
  const projectSlug = $derived(page.params.project ?? "");

  function load() {
    if (orgSlug && projectSlug) void agents.load(orgSlug, projectSlug).catch(() => {});
  }

  // 実 API から人格・活動・パイプラインを取得（issue 036）。
  $effect(() => {
    void orgSlug;
    void projectSlug;
    load();
  });

  // 返済ループ完了で活動/パイプラインを自動リフレッシュ（loop_agents → agents.load、issue 049）。
  refreshOnStageComplete(["loop_agents"], load);

  const pipeline = $derived(agents.visiblePipelines[0] ?? null);
</script>

<svelte:head>
  <title>{m.nav_agents()} · Rosetta</title>
</svelte:head>

<div class="mx-auto flex max-w-5xl flex-col gap-4 p-4">
  <!-- Code / Knowledge の切替 + モックである旨のラベル -->
  <Tabs.Root value={agents.selectedKind} onValueChange={(v) => (agents.selectedKind = v as AgentKind)}>
    <div class="flex items-center justify-between gap-2">
      <Tabs.List>
        <Tabs.Trigger value="code_debt">{m.agents_kind_code()}</Tabs.Trigger>
        <Tabs.Trigger value="knowledge_debt">{m.agents_kind_knowledge()}</Tabs.Trigger>
      </Tabs.List>
      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          class="h-7 px-2 text-xs"
          disabled={analysisRun.running}
          onclick={() => analysisRun.runAll({ orgSlug, projectSlug, owner: "", repo: "" })}
        >
          {m.agents_run_loop()}
        </Button>
        <span class="text-xs text-muted-foreground">{m.agents_preview_label()}</span>
      </div>
    </div>
  </Tabs.Root>

  {#if agents.profile}
    <AgentProfileHeader profile={agents.profile} />
  {/if}

  <div class="grid gap-4 lg:grid-cols-2">
    <!-- 左: ナラティブ思考ストリーム -->
    <section class="rounded-lg border bg-card p-4">
      <h2 class="mb-3 text-sm font-medium text-muted-foreground">{m.agents_stream_title()}</h2>
      <NarrativeStream activities={agents.visibleActivities} />
    </section>

    <!-- 右: 実行パイプライン + 未配線領域の Coming Soon -->
    <section class="flex flex-col gap-4">
      <div class="rounded-lg border bg-card p-4">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-sm font-medium text-muted-foreground">{m.agents_pipeline_title()}</h2>
          {#if pipeline}
            <Button variant="outline" size="sm" class="h-6 px-2 text-xs" onclick={() => agents.tick(pipeline.id)}>
              {m.agents_tick()}
            </Button>
          {/if}
        </div>
        {#if pipeline}<AgentPipeline {pipeline} />{/if}
      </div>
      <ComingSoonPlaceholder title={m.agents_coming_learning_title()} description={m.agents_coming_learning_desc()} />
    </section>
  </div>
</div>
