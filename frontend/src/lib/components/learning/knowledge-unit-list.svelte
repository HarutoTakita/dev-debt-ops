<script lang="ts">
  import { resolve } from "$app/paths";
  import { localizeDemoContent } from "$lib/i18n/demo-content";
  import type { ResolvedPathname } from "$app/types";
  import { getKnowledgeUnits, setUnitFlag } from "$lib/api/client";
  import type { KnowledgeUnit } from "$lib/api/schemas";
  import { cn } from "$lib/utils";
  import Flag from "@lucide/svelte/icons/flag";
  import { refreshOnStageComplete } from "$lib/stores/analysis-run-refresh.svelte";
  import PageHeading from "$lib/components/shell/page-heading.svelte";
  import * as m from "$lib/paraglide/messages";

  // 機能（feature）単位の単元ハブ（issue 063）。各単元で 学習 → 確認クイズ → KC 更新（理解済み）を回す。
  type Props = { orgSlug: string; projectSlug: string };
  const { orgSlug, projectSlug }: Props = $props();

  let units = $state<KnowledgeUnit[]>([]);
  let loading = $state(true);

  async function load() {
    loading = true;
    try {
      units = await getKnowledgeUnits(orgSlug, projectSlug);
    } catch {
      units = [];
    } finally {
      loading = false;
    }
  }
  $effect(() => {
    void orgSlug;
    void projectSlug;
    void load();
  });
  // agentic 解析（機能クラスタ・KC を内包）とプラン生成の完了で単元を再取得（issue 049/069）。
  refreshOnStageComplete(["agentic"], load);

  function kcPct(kc: number): number {
    return Math.round(Math.max(0, Math.min(1, kc)) * 100);
  }

  // フラグ付きを上部へ（同グループ内は元順序を保持＝安定ソート）。バックエンドの並びと一致させる。
  function sortByFlag(list: KnowledgeUnit[]): KnowledgeUnit[] {
    return list
      .map((u, i) => ({ u, i }))
      .sort((a, b) => Number(b.u.flagged) - Number(a.u.flagged) || a.i - b.i)
      .map((x) => x.u);
  }

  // フラグのトグル（楽観更新 → 失敗時ロールバック）。成功時は上部へ並べ替える。
  async function toggleFlag(u: KnowledgeUnit) {
    const next = !u.flagged;
    u.flagged = next;
    units = sortByFlag(units);
    try {
      await setUnitFlag(orgSlug, projectSlug, u.feature_key, next);
    } catch {
      u.flagged = !next;
      units = sortByFlag(units);
    }
  }
  const STATUS: Record<string, { label: () => string; tone: string }> = {
    unstarted: { label: m.unit_status_unstarted, tone: "text-muted-foreground" },
    in_progress: { label: m.unit_status_in_progress, tone: "text-debt-knowledge" },
    learned: { label: m.unit_status_learned, tone: "text-debt-knowledge" },
    verified: { label: m.unit_status_verified, tone: "text-success" },
    needs_review: { label: m.unit_status_needs_review, tone: "text-destructive" },
  };
  function statusOf(s: string) {
    return STATUS[s] ?? STATUS.unstarted;
  }

  // 苦手単元フィルタ（#4）: 確認クイズで低スコアだった単元（needs_review）だけに絞り込む。
  let showWeakOnly = $state(false);
  const weakCount = $derived(units.filter((u) => u.status === "needs_review").length);
  const visibleUnits = $derived(showWeakOnly ? units.filter((u) => u.status === "needs_review") : units);
</script>

<div class="mx-auto max-w-6xl space-y-4 p-4" data-tour="units-list">
  <PageHeading title={m.nav_knowledge_hub()} description={m.units_subtitle()} />

  {#if loading}
    <p class="py-8 text-center text-sm text-muted-foreground">…</p>
  {:else if units.length === 0}
    <p class="py-8 text-center text-sm text-muted-foreground">{m.units_empty()}</p>
  {:else}
    {#if weakCount > 0}
      <!-- 苦手単元フィルタ（#4）。 -->
      <div class="flex items-center gap-2 text-xs">
        <button
          type="button"
          onclick={() => (showWeakOnly = false)}
          class={cn(
            "rounded-full border px-2.5 py-1 font-medium",
            !showWeakOnly ? "border-foreground/30 bg-accent/50" : "text-muted-foreground hover:bg-accent/30",
          )}
        >
          {m.units_filter_all()}
        </button>
        <button
          type="button"
          onclick={() => (showWeakOnly = true)}
          class={cn(
            "rounded-full border px-2.5 py-1 font-medium",
            showWeakOnly
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "text-muted-foreground hover:bg-accent/30",
          )}
        >
          {m.units_filter_weak()} ({weakCount})
        </button>
      </div>
    {/if}
    {#if showWeakOnly && visibleUnits.length === 0}
      <p class="py-8 text-center text-sm text-muted-foreground">{m.units_weak_none()}</p>
    {/if}
    <ul class="flex flex-col gap-2">
      {#each visibleUnits as u (u.feature_key)}
        <li class="rounded-lg border bg-card p-3">
          <div class="flex items-center gap-3">
            <button
              type="button"
              onclick={() => toggleFlag(u)}
              aria-pressed={u.flagged}
              title={u.flagged ? m.unit_flag_remove() : m.unit_flag_add()}
              class={cn(
                "shrink-0 rounded p-1 hover:bg-accent/40",
                u.flagged ? "text-debt-knowledge" : "text-muted-foreground",
              )}
            >
              <Flag class="size-4" fill={u.flagged ? "currentColor" : "none"} />
            </button>
            <span class="min-w-0 flex-1 truncate font-medium">{localizeDemoContent(u.name)}</span>
            {#if u.learning_steps_total > 0}
              <!-- 学習プラン進捗（完了/総ステップ）。行内にコンパクト表示してブロック高さを増やさない。 -->
              <div
                class="hidden shrink-0 items-center gap-1.5 sm:flex"
                title="{m.learning_progress()} {u.learning_steps_done}/{u.learning_steps_total}"
              >
                <div class="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
                  <div
                    class="h-full rounded-full bg-debt-knowledge/60"
                    style="width: {Math.round((u.learning_steps_done / u.learning_steps_total) * 100)}%"
                  ></div>
                </div>
                <span class="text-xs tabular-nums text-muted-foreground"
                  >{u.learning_steps_done}/{u.learning_steps_total}</span
                >
              </div>
            {/if}
            <span class={cn("shrink-0 text-xs font-medium", statusOf(u.status).tone)}
              >{statusOf(u.status).label()}</span
            >
            <span class="shrink-0 text-xs text-muted-foreground">{m.kc_label()} {kcPct(u.knowledge_coverage)}%</span>
            <span class="hidden shrink-0 text-xs text-muted-foreground sm:inline"
              >{m.unit_files_count({ count: u.file_count })}</span
            >
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            {#if u.learning_plan_id}
              <a
                href={(resolve(`/${orgSlug}/${projectSlug}/learning`) +
                  `?planId=${u.learning_plan_id}`) as ResolvedPathname}
                data-tour="unit-learn"
                class="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-accent/40"
              >
                {m.unit_learn_open()}
              </a>
            {:else}
              <span class="text-xs text-muted-foreground">{m.unit_pending()}</span>
            {/if}
            {#if u.quiz_session_id}
              <a
                href={resolve(`/${orgSlug}/${projectSlug}/quizzes/${u.quiz_session_id}`)}
                data-tour="unit-confirm"
                class="rounded-md border px-2.5 py-1 text-xs font-medium text-debt-knowledge hover:bg-accent/40"
              >
                {m.unit_confirm()}
              </a>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>
